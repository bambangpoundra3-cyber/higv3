import os
import time
import random
import asyncio
import concurrent.futures
from requests import post, get
import urllib3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from threading import Thread
import re

# Suppress verify=False warning
urllib3.disable_warnings(category=urllib3.exceptions.InsecureRequestWarning)

# ==================== MISC ====================
session_cache = {}

class ReportOptions:
    def __init__(self):
        self.report_options = {
            1: "Spam",
            2: "Self", 
            3: "Drugs",
            4: "Nudity",
            5: "Violence", 
            6: "Hate",
        }
    
    def get_report_number(self, report_type: str) -> int:
        report_type = report_type.title()
        for number, name in self.report_options.items():
            if name == report_type:
                return number
        return 1

class Config:
    def __init__(self):
        self.sessions = []
        self.proxy_list = []
        self.working_proxies = []
        self.use_proxy = False
    
    def load_sessions(self, sessions_text):
        sessions = [s.strip() for s in sessions_text.split('\n') if s.strip()]
        if not sessions:
            return False
        self.sessions = sessions
        return True
    
    def load_proxies_from_file(self, file_content):
        """تحميل البروكسيات من محتوى الملف"""
        try:
            proxies = []
            for line in file_content.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    # تحويل من ip:port إلى http://ip:port
                    if not line.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                        line = f"http://{line}"
                    proxies.append(line)
            
            if not proxies:
                return False
                
            self.proxy_list = proxies
            return True
        except Exception as e:
            print(f"❌ خطأ في تحميل البروكسيات: {e}")
            return False

class ProxyManager:
    def __init__(self):
        self.blacklist = {}
        self.last_warning = 0
        
    def is_blacklisted(self, proxy):
        if proxy in self.blacklist:
            if time.time() < self.blacklist[proxy]:
                return True
            else:
                del self.blacklist[proxy]
        return False
    
    def blacklist_proxy(self, proxy, duration=60):
        self.blacklist[proxy] = time.time() + duration
        
    def get_available_proxy(self, proxy_list):
        available_proxies = [p for p in proxy_list if not self.is_blacklisted(p)]
        if not available_proxies:
            return None
        return random.choice(available_proxies)
    
    def test_proxy_fast(self, proxy):
        """🔍 فحص البروكسي السريع باستخدام مهلة قصيرة"""
        try:
            proxies = {
                "http": proxy,
                "https": proxy
            }
            # اختبار سريع للاتصال مع مهلة قصيرة
            test_url = "https://www.instagram.com"
            response = get(test_url, proxies=proxies, timeout=5, verify=False)
            return response.status_code == 200
        except:
            return False

class ReportBot:
    def __init__(self):
        self.active_reports = {}
        self.user_states = {}
        self.proxy_check_messages = {}  # تخزين رسائل تحديث الفحص
    
    def add_active_report(self, user_id, target_id, message_id, target_username=""):
        self.active_reports[user_id] = {
            'target_id': target_id,
            'target_username': target_username,
            'message_id': message_id,
            'start_time': time.time(),
            'stats': {
                'success': 0,
                'failed': 0,
                'failed_session': 0,
                'rate_limits': 0,
                'total_reports': 0
            },
            'running': True
        }
    
    def update_stats(self, user_id, stat_type):
        if user_id in self.active_reports:
            self.active_reports[user_id]['stats'][stat_type] += 1
            self.active_reports[user_id]['stats']['total_reports'] += 1
    
    def stop_report(self, user_id):
        if user_id in self.active_reports:
            self.active_reports[user_id]['running'] = False
            return True
        return False
    
    def get_report_status(self, user_id):
        return self.active_reports.get(user_id)
    
    def set_proxy_check_message(self, user_id, message_id):
        """تخزين معرف رسالة تحديث الفحص"""
        self.proxy_check_messages[user_id] = message_id
    
    def get_proxy_check_message(self, user_id):
        """الحصول على معرف رسالة تحديث الفحص"""
        return self.proxy_check_messages.get(user_id)

# ==================== INSTAGRAM API ====================
def get_csrf_token(sessionid):
    if sessionid in session_cache:
        return session_cache[sessionid]
    
    try:
        r1 = get(
            "https://www.instagram.com/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0",
            },
            cookies={"sessionid": sessionid},
            timeout=10
        )
        if "csrftoken" in r1.cookies:
            session_cache[sessionid] = r1.cookies["csrftoken"]
            return r1.cookies["csrftoken"]
    except:
        pass
    return None

def get_user_id_from_username(username):
    """🔍 استخراج الـ ID من اسم المستخدم - طريقة محسنة"""
    print(f"🔍 جاري البحث عن المستخدم: {username}")
    
    try:
        # الطريقة الأولى: GraphQL API
        url = f"https://www.instagram.com/{username}/?__a=1&__d=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.instagram.com/{username}/"
        }
        response = get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'graphql' in data and 'user' in data['graphql']:
                user_id = data['graphql']['user']['id']
                print(f"✅ تم العثور على الـ ID عبر GraphQL: {user_id}")
                return user_id
    except Exception as e:
        print(f"❌ فشلت طريقة GraphQL: {e}")
    
    try:
        # الطريقة الثانية: Web Profile API
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        headers = {
            "User-Agent": "Instagram 219.0.0.12.117 Android",
            "X-IG-App-ID": "936619743392459"
        }
        response = get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and 'user' in data['data']:
                user_id = data['data']['user']['id']
                print(f"✅ تم العثور على الـ ID عبر Web Profile: {user_id}")
                return user_id
    except Exception as e:
        print(f"❌ فشلت طريقة Web Profile: {e}")
    
    try:
        # الطريقة الثالثة: استخراج من HTML
        url = f"https://www.instagram.com/{username}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            html_content = response.text
            patterns = [
                r'"user_id":"(\d+)"',
                r'"profilePage_(\d+)"',
                r'"id":"(\d+)"',
                r'instagram://user\?id=(\d+)'
            ]
            for pattern in patterns:
                matches = re.findall(pattern, html_content)
                for match in matches:
                    if match.isdigit() and len(match) > 5:
                        print(f"✅ تم العثور على الـ ID عبر HTML: {match}")
                        return match
    except Exception as e:
        print(f"❌ فشلت طريقة HTML: {e}")
    
    print("❌ فشلت جميع الطرق في الحصول على الـ ID")
    return None

def extract_username_from_url(text):
    """🔍 استخراج اسم المستخدم من النص المدخل"""
    if not text or not text.strip():
        return None
        
    text = text.strip()
    
    if text.startswith('@'):
        text = text[1:]
    
    patterns = [
        r'(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?',
        r'([A-Za-z0-9_.]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            username = match.group(1)
            username = username.split('?')[0].split('/')[0].split('#')[0]
            if username and len(username) >= 1 and username != 'p' and username != 'reel':
                return username
    return None

def report_instagram_v11(target_id, sessionid, reportType, proxy=None):
    """📤 طريقة الإبلاغ v11 المحسنة"""
    try:
        if isinstance(proxy, str):
            proxy = {"http": proxy, "https": proxy}
        
        csrftoken = get_csrf_token(sessionid)
        if not csrftoken:
            print("❌ لا يوجد CSRF token متاح")
            return 400, False
            
        reportNumber = ReportOptions().get_report_number(reportType)
        
        print(f"📤 جاري إرسال بلاغ v11 للمستخدم {target_id} بسبب {reportNumber}")
        
        # استخدام واجهات متعددة لزيادة فرص النجاح
        endpoints = [
            f"https://i.instagram.com/users/{target_id}/flag/",
            f"https://i.instagram.com/api/v1/users/{target_id}/flag_user/",
        ]
        
        for endpoint in endpoints:
            try:
                headers = {
                    "User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(10, 11)}.0; Win64; x64; rv:{random.randint(90, 110)}.0) Gecko/20100101 Firefox/{random.randint(100, 120)}.0",
                    "Host": "i.instagram.com",
                    "cookie": f"sessionid={sessionid}",
                    "X-CSRFToken": csrftoken,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                }
                
                data = f'source_name=&reason_id={reportNumber}&frx_context='
                
                response = post(
                    endpoint,
                    headers=headers,
                    data=data,
                    proxies=proxy,
                    allow_redirects=False,
                    timeout=10,
                    verify=False
                )
                
                print(f"📡 الرد من {endpoint.split('/')[-1]}: {response.status_code}")
                
                if response.status_code == 200:
                    print("✅ نجح بلاغ v11!")
                    return response.status_code, True
                elif response.status_code == 429:
                    print("⚠️ تم تجاوز معدل الطلبات")
                    return response.status_code, False
                elif response.status_code == 400:
                    print("❌ طلب خاطئ - قد تكون الجلسة غير صالحة")
                    continue  # جرب النقطة الطرفية التالية
                    
            except Exception as e:
                print(f"❌ فشلت النقطة الطرفية {endpoint}: {e}")
                continue
        
        return 0, False
        
    except Exception as e:
        print(f"❌ خطأ في بلاغ v11: {e}")
        return 0, False

# ==================== TELEGRAM BOT ====================
report_bot = ReportBot()
TOKEN = ""

def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("🚀 بدء الإبلاغ", callback_data="start_report")],
        [InlineKeyboardButton("⏹ إيقاف الإبلاغ", callback_data="stop_report")],
        [InlineKeyboardButton("📊 الحالة الحالية", callback_data="current_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🛡️ *بوت إنستجرام للإبلاغ - النسخة v11*\n\n"
        "⚠️ *تحذير: للاستخدام الأخلاقي فقط*\n\n"
        "🔹 *المميزات الجديدة:*\n"
        "• إبلاغ v11 محسن وسريع 🚀\n"
        "• دعم جلسات متعددة 👥\n"
        "• نظام بروكسي متقدم 🔄\n"
        "• إحصائيات حية 📈\n"
        "• 🆕 إبلاغ متعدد الأنواع 🎯\n"
        "• 🆕 بلاغ سبام تلقائي 🤖\n\n"
        "اختر أحد الخيارات:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "start_report":
        report_bot.user_states[user_id] = 'waiting_target'
        query.edit_message_text(
            "🎯 *أدخل اسم المستخدم أو الرابط:*\n\n"
            "📝 *الأمثلة المدعومة:*\n"
            "• `username`\n"
            "• `@username`\n" 
            "• `https://instagram.com/username`\n"
            "• `instagram.com/username`\n\n"
            "🔍 *ملاحظة:* يستخدم البوت طرق متقدمة لاكتشاف الحسابات",
            parse_mode='Markdown'
        )
    
    elif query.data == "stop_report":
        if report_bot.stop_report(user_id):
            query.edit_message_text("✅ تم إيقاف عملية الإبلاغ بنجاح")
        else:
            query.edit_message_text("❌ لا توجد عملية إبلاغ نشطة لإيقافها")
    
    elif query.data == "current_status":
        status = report_bot.get_report_status(user_id)
        if status:
            stats = status['stats']
            elapsed = int(time.time() - status['start_time'])
            text = f"📊 *حالة الإبلاغ الحالية:*\n\n"
            text += f"🎯 الهدف: {status['target_username'] or status['target_id']}\n"
            text += f"⏱ الوقت المنقضي: {elapsed} ثانية\n"
            text += f"✅ بلاغات ناجحة: {stats['success']}\n"
            text += f"❌ بلاغات فاشلة: {stats['failed']}\n"
            text += f"🔴 جلسات فاشلة: {stats['failed_session']}\n"
            text += f"📈 إجمالي البلاغات: {stats['total_reports']}\n\n"
            text += f"🟢 *الحالة: نشط*"
            query.edit_message_text(text, parse_mode='Markdown')
        else:
            query.edit_message_text("❌ لا توجد عملية إبلاغ نشطة")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text
    
    print(f"📨 تم استلام رسالة من المستخدم {user_id}: {text}")
    
    if user_id not in report_bot.user_states:
        update.message.reply_text("❌ استخدم الأزرار للبدء")
        return
    
    state = report_bot.user_states[user_id]
    
    if state == 'waiting_target':
        handle_target_input(update, text, user_id)
    
    elif isinstance(state, dict):
        current_step = state.get('step')
        
        if current_step == 'waiting_sessions':
            handle_session_input(update, text, user_id)
        
        elif current_step == 'waiting_report_mode':
            handle_report_mode(update, text, user_id)
        
        elif current_step == 'waiting_single_report':
            handle_single_report(update, text, user_id)
        
        elif current_step == 'waiting_multi_reports':
            handle_multi_reports(update, text, user_id)
        
        elif current_step == 'waiting_auto_spam':
            handle_auto_spam(update, text, user_id)

def handle_document(update: Update, context: CallbackContext):
    """📁 معالجة استقبال ملف البروكسيات"""
    user_id = update.effective_user.id
    
    if user_id not in report_bot.user_states:
        update.message.reply_text("❌ استخدم الأزرار للبدء أولاً")
        return
    
    state = report_bot.user_states[user_id]
    if not isinstance(state, dict) or state.get('step') != 'waiting_proxies_file':
        update.message.reply_text("❌ لست في مرحلة تحميل البروكسيات")
        return
    
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        update.message.reply_text("❌ يرجى إرسال ملف نصي بصيغة .txt فقط")
        return
    
    # تحميل الملف
    file = context.bot.get_file(document.file_id)
    file_path = f"proxies_{user_id}.txt"
    file.download(file_path)
    
    # قراءة محتوى الملف
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        # حذف الملف المؤقت
        os.remove(file_path)
        
        # بدء فحص البروكسيات في thread منفصل
        thread = Thread(target=handle_proxies_file_fast, args=(update, context, file_content, user_id))
        thread.daemon = True
        thread.start()
        
    except Exception as e:
        update.message.reply_text(f"❌ خطأ في قراءة الملف: {e}")

def handle_proxies_file_fast(update, context, file_content, user_id):
    """🌐 فحص البروكسيات السريع مع تحديث حي"""
    config = report_bot.user_states[user_id]['config']
    
    # إرسال رسالة بدء الفحص
    progress_msg = update.message.reply_text("🚀 بدأ الفحص السريع للبروكسيات...")
    report_bot.set_proxy_check_message(user_id, progress_msg.message_id)
    
    if config.load_proxies_from_file(file_content):
        proxy_manager = ProxyManager()
        total_proxies = len(config.proxy_list)
        
        # تحديث الرسالة بالمعلومات الأولية
        context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=progress_msg.message_id,
            text=f"🚀 *بدأ الفحص السريع للبروكسيات*\n\n"
                 f"📊 الإجمالي: {total_proxies} بروكسي\n"
                 f"✅ الشغالة: 0\n"
                 f"❌ الفاشلة: 0\n"
                 f"⏳ جاري الفحص: {total_proxies}\n\n"
                 f"⚡ *الفحص يعمل بسرعة عالية...*",
            parse_mode='Markdown'
        )
        
        # فحص البروكسيات باستخدام ThreadPoolExecutor للسرعة
        working_proxies = []
        checked_count = 0
        
        def check_proxy(proxy):
            return proxy, proxy_manager.test_proxy_fast(proxy)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            future_to_proxy = {executor.submit(check_proxy, proxy): proxy for proxy in config.proxy_list}
            
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy, is_working = future.result()
                checked_count += 1
                
                if is_working:
                    working_proxies.append(proxy)
                    print(f"✅ البروكسي شغال: {proxy}")
                else:
                    print(f"❌ البروكسي فاشل: {proxy}")
                
                # تحديث الرسالة كل 10 بروكسيات أو عند الانتهاء
                if checked_count % 10 == 0 or checked_count == total_proxies:
                    try:
                        context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=progress_msg.message_id,
                            text=f"🚀 *جاري الفحص السريع للبروكسيات*\n\n"
                                 f"📊 الإجمالي: {total_proxies} بروكسي\n"
                                 f"✅ الشغالة: {len(working_proxies)}\n"
                                 f"❌ الفاشلة: {checked_count - len(working_proxies)}\n"
                                 f"⏳ المتبقية: {total_proxies - checked_count}\n"
                                 f"📈 النسبة: {round((len(working_proxies) / total_proxies) * 100, 1)}%\n\n"
                                 f"⚡ *الفحص يعمل بسرعة عالية...*",
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        print(f"⚠️ خطأ في تحديث الرسالة: {e}")
        
        config.working_proxies = working_proxies
        config.use_proxy = True
        
        # الرسالة النهائية
        success_rate = round((len(working_proxies) / total_proxies) * 100, 1) if total_proxies > 0 else 0
        
        if working_proxies:
            context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=progress_msg.message_id,
                text=f"🎉 *تم الانتهاء من الفحص السريع!*\n\n"
                     f"📊 *النتائج النهائية:*\n"
                     f"• 📥 الإجمالي: {total_proxies} بروكسي\n"
                     f"• ✅ الشغالة: {len(working_proxies)}\n"
                     f"• ❌ الفاشلة: {total_proxies - len(working_proxies)}\n"
                     f"• 📈 نسبة النجاح: {success_rate}%\n\n"
                     f"🎯 *جاهز للبدء بالإبلاغ المتقدم*",
                parse_mode='Markdown'
            )
        else:
            context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=progress_msg.message_id,
                text=f"⚠️ *تم الانتهاء من الفحص*\n\n"
                     f"❌ *لم يتم العثور على بروكسيات شغالة!*\n\n"
                     f"📊 الإجمالي: {total_proxies} بروكسي\n"
                     f"✅ الشغالة: 0\n"
                     f"❌ الفاشلة: {total_proxies}\n\n"
                     f"🔧 جاري المتابعة بدون بروكسي",
                parse_mode='Markdown'
            )
            config.use_proxy = False
    else:
        context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=progress_msg.message_id,
            text="❌ *لم يتم العثور على بروكسيات صالحة في الملف!*\n\n"
                 "تأكد من تنسيق الملف:\n"
                 "• كل بروكسي في سطر منفصل\n"
                 "• التنسيق: `ip:port` أو `ip:port:user:pass`\n\n"
                 "🔧 جاري المتابعة بدون بروكسي",
            parse_mode='Markdown'
        )
        config.use_proxy = False
    
    report_bot.user_states[user_id]['step'] = 'waiting_report_mode'
    
    # إرسال لوحة اختيار نمط الإبلاغ بعد ثانيتين
    time.sleep(2)
    send_report_mode_keyboard(update.message)

def handle_target_input(update, text, user_id):
    """🎯 معالجة إدخال الهدف"""
    username = extract_username_from_url(text)
    
    if not username:
        update.message.reply_text(
            "❌ *لم أستطع التعرف على اسم المستخدم!*\n\n"
            "تأكد من استخدام التنسيقات المدعومة وحاول مرة أخرى:",
            parse_mode='Markdown'
        )
        return
    
    update.message.reply_text(f"🔍 جاري البحث عن: @{username}...")
    
    target_id = get_user_id_from_username(username)
    
    if target_id:
        report_bot.user_states[user_id] = {
            'target_id': target_id,
            'target_username': username,
            'step': 'waiting_sessions'
        }
        update.message.reply_text(
            f"✅ *تم العثور على المستخدم!*\n"
            f"👤 المستخدم: @{username}\n"
            f"🆔 الـ ID: `{target_id}`\n\n"
            f"🔐 *الآن أدخل الـ Session IDs:*\n\n"
            "أرسل الـ sessionids كل واحد في سطر:\n"
            "📝 *مثال:*\n"
            "sessionid123\n"
            "sessionid456\n"
            "sessionid789",
            parse_mode='Markdown'
        )
    else:
        update.message.reply_text(
            "❌ *لم أتمكن من العثور على المستخدم!*\n\n"
            "🔍 *الأسباب المحتملة:*\n"
            "• الحساب غير موجود\n"
            "• الحساب خاص\n"
            "• اسم المستخدم خطأ\n\n"
            "🔄 حاول مرة أخرى:",
            parse_mode='Markdown'
        )

def handle_session_input(update, text, user_id):
    """🔐 معالجة إدخال الجلسات"""
    config = Config()
    if config.load_sessions(text):
        # اختبار الجلسات قبل المتابعة
        valid_sessions = []
        for session in config.sessions:
            csrf = get_csrf_token(session)
            if csrf:
                valid_sessions.append(session)
                print(f"✅ الجلسة صالحة: {session[:15]}...")
            else:
                print(f"❌ الجلسة غير صالحة: {session[:15]}...")
        
        if valid_sessions:
            config.sessions = valid_sessions
            report_bot.user_states[user_id]['config'] = config
            report_bot.user_states[user_id]['step'] = 'waiting_proxy_choice'
            
            keyboard = [[InlineKeyboardButton("نعم ✅", callback_data="use_proxy_yes"),
                       InlineKeyboardButton("لا ❌", callback_data="use_proxy_no")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                f"✅ *تم تحميل {len(valid_sessions)} جلسة صالحة من أصل {len(config.sessions)}!*\n\n"
                f"🌐 *هل تريد استخدام بروكسي؟*\n\n"
                f"💡 *مميزات البروكسي:*\n"
                f"• حماية هويتك 🛡️\n"
                f"• تجنب الحظر 🔄\n"
                f"• سرعة أفضل 🚀",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text(
                "❌ *جميع الجلسات غير صالحة!*\n\n"
                "تأكد من صحة الـ sessionids وحاول مرة أخرى:",
                parse_mode='Markdown'
            )
    else:
        update.message.reply_text("❌ لم يتم إدخال أي sessionids صالحة")

def handle_report_mode(update, text, user_id):
    """🎛️ معالجة اختيار نمط الإبلاغ"""
    if text == '1':
        report_bot.user_states[user_id]['step'] = 'waiting_single_report'
        send_report_type_keyboard(update.message)
    elif text == '2':
        report_bot.user_states[user_id]['step'] = 'waiting_multi_reports'
        update.message.reply_text(
            "🔄 *وضع الإبلاغ المتعدد*\n\n"
            "📝 *أدخل البلاغات بالشكل التالي:*\n\n"
            "`عدد النوع`\n\n"
            "📋 *الأمثلة:*\n"
            "`10 Hate`\n"
            "`5 Self`\n"
            "`3 Violence`\n\n"
            "💡 *يمكنك إدخال أكثر من بلاغ، كل بلاغ في سطر:*\n"
            "10 Hate\n"
            "5 Self\n"
            "3 Violence\n\n"
            "🔍 *الأنواع المدعومة:*\n"
            "• Spam\n• Self\n• Drugs\n• Nudity\n• Violence\n• Hate",
            parse_mode='Markdown'
        )
    else:
        update.message.reply_text("❌ اختر 1 أو 2 فقط")

def handle_single_report(update, text, user_id):
    """🔸 معالجة البلاغ المفرد"""
    try:
        reports_count = int(text.strip())
        if reports_count <= 0:
            update.message.reply_text("❌ العدد يجب أن يكون أكبر من الصفر")
            return
        
        state = report_bot.user_states[user_id]
        state['reports'] = [{'type': state['report_type'], 'count': reports_count}]
        state['step'] = 'waiting_auto_spam'
        
        keyboard = [[InlineKeyboardButton("نعم ✅", callback_data="auto_spam_yes"),
                   InlineKeyboardButton("لا ❌", callback_data="auto_spam_no")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "🔄 *تفعيل البلاغ التلقائي للسبام*\n\n"
            "هل تريد إضافة بلاغ سبام تلقائي مع كل البلاغات؟\n\n"
            "📊 *مثال:*\n"
            "سيتم إرسال 10 بلاغات من النوع المحدد\n"
            "+ بلاغ سبام إضافي مع كل بلاغ\n\n"
            "💡 *هذا يزيد من فعالية الإبلاغ*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except ValueError:
        update.message.reply_text("❌ أدخل رقماً صحيحاً")

def handle_multi_reports(update, text, user_id):
    """🔄 معالجة البلاغات المتعددة"""
    lines = text.strip().split('\n')
    reports = []
    total_reports = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        parts = line.split(' ', 1)
        if len(parts) != 2:
            update.message.reply_text(f"❌ تنسيق خاطئ: {line}\nاستخدم: 'عدد النوع'")
            return
        
        try:
            count = int(parts[0])
            report_type = parts[1].strip().title()
            
            # التحقق من صحة النوع
            valid_types = ["Spam", "Self", "Drugs", "Nudity", "Violence", "Hate"]
            if report_type not in valid_types:
                update.message.reply_text(f"❌ نوع غير صحيح: {report_type}\nالأنواع الصحيحة: {', '.join(valid_types)}")
                return
            
            reports.append({'type': report_type, 'count': count})
            total_reports += count
            
        except ValueError:
            update.message.reply_text(f"❌ عدد غير صحيح: {parts[0]}")
            return
    
    if not reports:
        update.message.reply_text("❌ لم يتم إدخال أي بلاغات صحيحة")
        return
    
    if total_reports > 1000:
        update.message.reply_text("❌ إجمالي البلاغات يتجاوز 1000، الرجاء تقليل العدد")
        return
    
    report_bot.user_states[user_id]['reports'] = reports
    report_bot.user_states[user_id]['step'] = 'waiting_auto_spam'
    
    # عرض ملخص البلاغات
    summary = "📋 *ملخص البلاغات:*\n\n"
    for report in reports:
        summary += f"• {report['count']} {report['type']}\n"
    summary += f"\n📊 الإجمالي: {total_reports} بلاغ\n\n"
    
    keyboard = [[InlineKeyboardButton("نعم ✅", callback_data="auto_spam_yes"),
               InlineKeyboardButton("لا ❌", callback_data="auto_spam_no")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        summary + 
        "🔄 *تفعيل البلاغ التلقائي للسبام*\n\n"
        "هل تريد إضافة بلاغ سبام تلقائي مع كل البلاغات؟",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def handle_auto_spam(update, text, user_id):
    """🤖 معالجة اختيار البلاغ التلقائي للسبام"""
    if text.lower() in ['نعم', 'yes', 'y']:
        report_bot.user_states[user_id]['auto_spam'] = True
        update.message.reply_text("✅ تم تفعيل البلاغ التلقائي للسبام")
    else:
        report_bot.user_states[user_id]['auto_spam'] = False
        update.message.reply_text("❌ لم يتم تفعيل البلاغ التلقائي للسبام")
    
    # بدء عملية الإبلاغ
    start_reporting_process(update, user_id)

def start_reporting_process(update, user_id):
    """🚀 بدء عملية الإبلاغ"""
    state = report_bot.user_states[user_id]
    config = state['config']
    target_id = state['target_id']
    target_username = state['target_username']
    reports = state['reports']
    auto_spam = state.get('auto_spam', False)
    
    # بناء نص الحالة
    status_text = f"🚀 *بدء الإبلاغ - النسخة v11*\n\n"
    status_text += f"🎯 الهدف: {target_username}\n"
    status_text += f"🆔 ID: `{target_id}`\n"
    status_text += f"👥 الجلسات الصالحة: {len(config.sessions)}\n"
    status_text += f"🌐 البروكسي: {'✅ نعم' if config.use_proxy else '❌ لا'}\n"
    if config.use_proxy:
        status_text += f"🔗 البروكسيات الشغالة: {len(config.working_proxies)}\n"
    status_text += f"🔧 الطريقة: v11 Report المحسنة\n\n"
    
    status_text += "📋 *البلاغات المطلوبة:*\n"
    total_reports = 0
    for report in reports:
        status_text += f"• {report['count']} {report['type']}\n"
        total_reports += report['count']
    
    if auto_spam:
        status_text += f"• + بلاغ سبام تلقائي مع كل بلاغ\n"
        total_reports *= 2  # لأن كل بلاغ يصبح بلاغين (البلاغ الأصلي + سبام)
    
    status_text += f"\n📊 الإجمالي التقريبي: {total_reports} بلاغ\n\n"
    status_text += f"⏳ جاري البدء..."
    
    # الحصول على chat_id بشكل صحيح من update
    if update.message:
        chat_id = update.message.chat_id
        status_message = update.message.reply_text(status_text, parse_mode='Markdown')
    else:
        # في حالة callback query
        chat_id = update.callback_query.message.chat_id
        status_message = update.callback_query.message.reply_text(status_text, parse_mode='Markdown')
    
    thread = Thread(target=run_advanced_reporting, args=(user_id, target_id, target_username, config, reports, auto_spam, status_message.message_id, chat_id))
    thread.daemon = True
    thread.start()
    
    del report_bot.user_states[user_id]

def proxy_choice_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "use_proxy_yes":
        report_bot.user_states[user_id]['step'] = 'waiting_proxies_file'
        query.edit_message_text(
            "📁 *أرسل ملف البروكسيات الآن:*\n\n"
            "📝 *شروط الملف:*\n"
            "• يجب أن يكون بصيغة .txt\n"
            "• كل بروكسي في سطر منفصل\n"
            "• التنسيق المطلوب: `ip:port`\n\n"
            "🔗 *أمثلة على التنسيق:*\n"
            "`192.168.1.1:8080`\n"
            "`123.456.789.0:3128`\n"
            "`proxy.example.com:8080`\n\n"
            "⚡ *مميزات الفحص الجديد:*\n"
            "• فحص فائق السرعة (50 بروكسي في نفس الوقت)\n"
            "• تحديث حي للنتائج كل ثانية\n"
            "• تقرير مفصل بنسبة النجاح\n"
            "• استخدام البروكسيات الشغالة فقط\n\n"
            "📤 أرسل ملف txt الآن...",
            parse_mode='Markdown'
        )
    
    elif query.data == "use_proxy_no":
        report_bot.user_states[user_id]['config'].use_proxy = False
        report_bot.user_states[user_id]['step'] = 'waiting_report_mode'
        send_report_mode_keyboard(query.message)

def auto_spam_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    choice = query.data
    
    if choice == "auto_spam_yes":
        report_bot.user_states[user_id]['auto_spam'] = True
        query.edit_message_text("✅ تم تفعيل البلاغ التلقائي للسبام")
    else:
        report_bot.user_states[user_id]['auto_spam'] = False
        query.edit_message_text("❌ لم يتم تفعيل البلاغ التلقائي للسبام")
    
    # بدء عملية الإبلاغ - تمرير update بدلاً من query
    start_reporting_process(update, user_id)

def send_report_mode_keyboard(message):
    keyboard = [
        [InlineKeyboardButton("🔸 بلاغ واحد", callback_data="report_mode_single")],
        [InlineKeyboardButton("🔄 بلاغات متعددة", callback_data="report_mode_multi")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message.reply_text(
        "🎛️ *اختر نمط الإبلاغ:*\n\n"
        "🔸 *بلاغ واحد:*\n"
        "• بلاغ واحد بنوع محدد\n"
        "• مناسب للتركيز على نوع معين\n\n"
        "🔄 *بلاغات متعددة:*\n"
        "• عدة بلاغات بأنواع مختلفة\n"
        "• مثال: 10 Hate + 5 Self\n"
        "• يزيد من فعالية الإبلاغ",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def report_mode_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "report_mode_single":
        report_bot.user_states[user_id]['step'] = 'waiting_single_report'
        query.edit_message_text("✅ تم اختيار نمط البلاغ الواحد")
        send_report_type_keyboard(query.message)
    
    elif query.data == "report_mode_multi":
        report_bot.user_states[user_id]['step'] = 'waiting_multi_reports'
        query.edit_message_text(
            "🔄 *وضع الإبلاغ المتعدد*\n\n"
            "📝 *أدخل البلاغات بالشكل التالي:*\n\n"
            "`عدد النوع`\n\n"
            "📋 *الأمثلة:*\n"
            "`10 Hate`\n"
            "`5 Self`\n"
            "`3 Violence`\n\n"
            "💡 *يمكنك إدخال أكثر من بلاغ، كل بلاغ في سطر:*\n"
            "10 Hate\n"
            "5 Self\n"
            "3 Violence\n\n"
            "🔍 *الأنواع المدعومة:*\n"
            "• Spam\n• Self\n• Drugs\n• Nudity\n• Violence\n• Hate",
            parse_mode='Markdown'
        )

def send_report_type_keyboard(message):
    report_options = ReportOptions()
    
    keyboard = []
    for num, name in report_options.report_options.items():
        keyboard.append([InlineKeyboardButton(f"{num}. {name}", callback_data=f"report_type_{num}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message.reply_text(
        "📝 *اختر نوع الإبلاغ:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def report_type_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    report_type = int(query.data.split('_')[2])
    report_type_name = ReportOptions().report_options[report_type]
    
    report_bot.user_states[user_id]['report_type'] = report_type_name
    report_bot.user_states[user_id]['step'] = 'waiting_single_report'
    
    query.edit_message_text(
        f"✅ تم اختيار: {report_type_name}\n\n"
        f"🔢 *أدخل عدد البلاغات:*\n\n"
        f"📊 *مثال:* 50 (سيعمل 50 بلاغ من نوع {report_type_name})",
        parse_mode='Markdown'
    )

def run_advanced_reporting(user_id, target_id, target_username, config, reports, auto_spam, message_id, chat_id):
    """🚀 تشغيل عملية الإبلاغ v11 في thread منفصل"""
    print(f"🚀 بدء الإبلاغ المتقدم للمستخدم {user_id}")
    print(f"🎯 الهدف: {target_username} (ID: {target_id})")
    print(f"📊 البلاغات: {reports}")
    print(f"🔄 السبام التلقائي: {auto_spam}")
    
    report_bot.add_active_report(user_id, target_id, message_id, target_username)
    update_status_message_sync(user_id, chat_id, "🟢 بدأ الإبلاغ...")
    
    proxy_manager = ProxyManager() if config.use_proxy else None
    report_status = report_bot.get_report_status(user_id)
    
    try:
        session_index = 0
        total_reports_sent = 0
        
        while report_status['running'] and session_index < len(config.sessions):
            sessionid = config.sessions[session_index]
            print(f"🔑 استخدام الجلسة {session_index + 1}/{len(config.sessions)}: {sessionid[:15]}...")
            
            # تنفيذ جميع البلاغات المطلوبة لهذه الجلسة
            for report in reports:
                if not report_status['running']:
                    break
                
                report_type = report['type']
                report_count = report['count']
                
                print(f"📦 معالجة {report_count} بلاغ {report_type}")
                
                for i in range(report_count):
                    if not report_status['running']:
                        break
                    
                    # إرسال البلاغ الرئيسي
                    proxy = None
                    if config.use_proxy and proxy_manager and config.working_proxies:
                        proxy = proxy_manager.get_available_proxy(config.working_proxies)
                        if not proxy:
                            time.sleep(1)
                            continue
                    
                    print(f"📤 إرسال بلاغ {report_type} {i+1}/{report_count}")
                    status_code, success = report_instagram_v11(target_id, sessionid, report_type, proxy)
                    
                    if success:
                        report_bot.update_stats(user_id, 'success')
                        total_reports_sent += 1
                        print(f"✅ نجح بلاغ {report_type} (الإجمالي: {total_reports_sent})")
                    else:
                        report_bot.update_stats(user_id, 'failed')
                        print(f"❌ فشل بلاغ {report_type}")
                    
                    # إرسال بلاغ السبام التلقائي إذا مفعل
                    if auto_spam and report_status['running']:
                        spam_status_code, spam_success = report_instagram_v11(target_id, sessionid, "Spam", proxy)
                        
                        if spam_success:
                            report_bot.update_stats(user_id, 'success')
                            total_reports_sent += 1
                            print(f"✅ نجح بلاغ السبام التلقائي (الإجمالي: {total_reports_sent})")
                        else:
                            report_bot.update_stats(user_id, 'failed')
                            print(f"❌ فشل بلاغ السبام التلقائي")
                    
                    update_status_message_sync(user_id, chat_id, "🟢 جاري الإبلاغ...")
                    
                    # تأخير عشوائي محسن
                    delay = random.uniform(1, 3) if config.use_proxy else random.uniform(3, 7)
                    time.sleep(delay)
            
            session_index += 1
            
            if session_index < len(config.sessions) and report_status['running']:
                time.sleep(2)  # تأخير أقل بين الجلسات
        
        # إعادة البدء إذا كانت هناك جلسات صالحة
        if report_status['running'] and len(config.sessions) > 0:
            print("🔄 إعادة البدء من الجلسة الأولى...")
            update_status_message_sync(user_id, chat_id, "🔄 إعادة بدء الدور...")
            time.sleep(2)
            run_advanced_reporting(user_id, target_id, target_username, config, reports, auto_spam, message_id, chat_id)
        
        if not report_status['running']:
            update_status_message_sync(user_id, chat_id, "🟡 متوقف")
            print("🛑 توقف الإبلاغ بواسطة المستخدم")
        
    except Exception as e:
        print(f"❌ خطأ في الإبلاغ المتقدم: {e}")
        update_status_message_sync(user_id, chat_id, f"🔴 خطأ: {str(e)}")

def update_status_message_sync(user_id, chat_id, status_text):
    """🔄 تحديث رسالة الحالة بشكل متزامن"""
    try:
        report_status = report_bot.get_report_status(user_id)
        if report_status:
            stats = report_status['stats']
            elapsed = int(time.time() - report_status['start_time'])
            
            text = f"✅ بلاغات ناجحة: {stats['success']}\n"
            text += f"❌ بلاغات فاشلة: {stats['failed']}\n"
            text += f"🎯 الهدف: {report_status['target_username'] or report_status['target_id']}\n"
            text += f"⏱ الوقت: {elapsed}ث\n"
            text += f"📊 الإجمالي: {stats['total_reports']}\n"
            text += f"🔴 جلسات فاشلة: {stats['failed_session']}\n\n"
            text += f"*{status_text}*"
            
            from telegram import Bot
            bot = Bot(token=TOKEN)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=report_status['message_id'],
                text=text,
                parse_mode='Markdown'
            )
    except Exception as e:
        print(f"❌ خطأ في تحديث الحالة: {e}")

def get_bot_token():
    """🔑 طلب التوكن من المستخدم عند التشغيل"""
    print("=" * 50)
    print("🤖 بوت إنستجرام للإبلاغ - النسخة v11")
    print("=" * 50)
    
    # محاولة قراءة التوكن من ملف إذا موجود
    try:
        with open("bot_token.txt", "r", encoding='utf-8') as f:
            saved_token = f.read().strip()
            if saved_token:
                use_saved = input(f"🔑 تم العثور على توكن محفوظ. هل تريد استخدامه؟ (y/n): ").lower()
                if use_saved == 'y':
                    return saved_token
    except:
        pass
    
    # طلب التوكن من المستخدم
    while True:
        token = input("🔑 أدخل توكن بوت التلغرام: ").strip()
        
        if not token:
            print("❌ يجب إدخال التوكن!")
            continue
            
        # التحقق من صحة التوكن الأساسي
        if len(token) < 30:
            print("❌ التوكن غير صحيح! تأكد من إدخال التوكن كاملاً")
            continue
            
        # حفظ التوكن في ملف
        save = input("💾 هل تريد حفظ التوكن للمستقبل؟ (y/n): ").lower()
        if save == 'y':
            try:
                with open("bot_token.txt", "w", encoding='utf-8') as f:
                    f.write(token)
                print("✅ تم حفظ التوكن في ملف bot_token.txt")
            except:
                print("⚠️ لم يتمكن من حفظ التوكن في الملف")
        
        return token

def main():
    global TOKEN
    
    # الحصول على التوكن من المستخدم
    TOKEN = get_bot_token()
    
    if not TOKEN:
        print("❌ لم يتم إدخال التوكن!")
        return
    
    # التحقق من صحة التوكن
    print("🔍 جاري التحقق من التوكن...")
    try:
        from telegram import Bot
        bot = Bot(token=TOKEN)
        bot_info = bot.get_me()
        print(f"✅ التوكن صحيح! البوت: @{bot_info.username}")
    except Exception as e:
        print(f"❌ التوكن غير صحيح: {e}")
        return
    
    # إنشاء التطبيق باستخدام Updater (النسخة القديمة المتوافقة)
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # إضافة جميع الـ handlers المطلوبة
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler, pattern="^(start_report|stop_report|current_status)$"))
    dispatcher.add_handler(CallbackQueryHandler(proxy_choice_handler, pattern="^use_proxy_"))
    dispatcher.add_handler(CallbackQueryHandler(report_mode_handler, pattern="^report_mode_"))
    dispatcher.add_handler(CallbackQueryHandler(report_type_handler, pattern="^report_type_"))
    dispatcher.add_handler(CallbackQueryHandler(auto_spam_handler, pattern="^auto_spam_"))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dispatcher.add_handler(MessageHandler(Filters.document, handle_document))
    
    # بدء البوت
    print("\n" + "=" * 50)
    print("🚀 البوت المتقدم يعمل الآن!")
    print("🔗 إذهب إلى بوتك في التلغرام وأرسل /start")
    print("⏹ لإيقاف البوت: Ctrl+C")
    print("=" * 50)
    
    try:
        updater.start_polling()
        print("✅ تم بدء البوت بنجاح!")
        updater.idle()
    except KeyboardInterrupt:
        print("\n⏹ تم إيقاف البوت")
    except Exception as e:
        print(f"❌ خطأ في تشغيل البوت: {e}")

if __name__ == "__main__":
    main()