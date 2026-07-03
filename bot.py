import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
import json
import os
from keep_alive import keep_alive

# إعداد الصلاحيات الأساسية للبوت
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ==================== 💾 حفظ وتحميل البيانات ====================

DATA_FILE = "points_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # ترقية البيانات القديمة تلقائياً
        if "event_points" not in data:
            data["event_points"] = data.get("user_points", {}).copy()
        if "regular_points" not in data:
            data["regular_points"] = {}
        if "saved_questions" not in data:
            data["saved_questions"] = {}
        return data
    return {
        "saved_questions": {},
        "event_points": {},
        "regular_points": {},
        "staff_points": {}
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==================== 🔐 نظام الصلاحيات العامة ====================

# رتب طاقم الإدارة والإيفينت (للأوامر العامة)
STAFF_ROLES = [
    "Owner", "Co-Owner", "Founder", "Manager",
    "Permission", "E.S.D CEO",
    "E.S.D Trainee", "E.S.D Junior", "E.S.D Helper", "E.S.D Professional",
]

def is_staff(ctx):
    try:
        if ctx.guild and ctx.author.id == ctx.guild.owner_id:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        member_roles_lower = [r.name.lower().strip() for r in ctx.author.roles]
        staff_roles_lower  = [r.lower().strip() for r in STAFF_ROLES]
        matched = any(r in member_roles_lower for r in staff_roles_lower)
        if not matched:
            print(f"[ACCESS DENIED] {ctx.author} | رتبه: {[r.name for r in ctx.author.roles]}")
        return matched
    except Exception as e:
        print(f"[is_staff ERROR] {e}")
        return False

def staff_only():
    async def predicate(ctx):
        if not is_staff(ctx):
            await ctx.send("🚫 هذا الأمر مخصص لطاقم الإدارة والإيفينت فقط.")
            return False
        return True
    return commands.check(predicate)

# ==================== 🔑 صلاحيات أمر !نقاط ====================

# الرتب المسموح لها بإضافة نقاط الإيفينت
POINTS_CMD_ROLES = [
    "Permission", "E.S.D CEO",
    "Owner", "Co-Owner", "Founder", "Manager",
]

def is_points_admin(ctx):
    try:
        if ctx.guild and ctx.author.id == ctx.guild.owner_id:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        member_roles_lower = [r.name.lower().strip() for r in ctx.author.roles]
        allowed_lower = [r.lower().strip() for r in POINTS_CMD_ROLES]
        matched = any(r in member_roles_lower for r in allowed_lower)
        if not matched:
            print(f"[POINTS DENIED] {ctx.author} | رتبه: {[r.name for r in ctx.author.roles]}")
        return matched
    except Exception as e:
        print(f"[is_points_admin ERROR] {e}")
        return False

def points_admin_only():
    async def predicate(ctx):
        if not is_points_admin(ctx):
            await ctx.send(
                "🚫 هذا الأمر مخصص للإدارة العليا فقط.\n"
                "`Permission / E.S.D CEO / Owner / Co-Owner / Founder / Manager`"
            )
            return False
        return True
    return commands.check(predicate)

# ==================== 🎖️ نظام الترقية التلقائية ====================

ROLE_TRAINEE      = "E.S.D Trainee"
ROLE_JUNIOR       = "E.S.D Junior"
ROLE_HELPER       = "E.S.D Helper"
ROLE_PROFESSIONAL = "E.S.D Professional"

PROMOTION_MAP = [
    (ROLE_TRAINEE,    ROLE_JUNIOR,       15),
    (ROLE_JUNIOR,     ROLE_HELPER,       35),
    (ROLE_HELPER,     ROLE_PROFESSIONAL, 50),
]

async def auto_promote(member: discord.Member, new_points: int, channel):
    member_role_names = [r.name for r in member.roles]
    guild = member.guild

    for current_role_name, next_role_name, threshold in PROMOTION_MAP:
        if current_role_name not in member_role_names:
            continue
        if new_points < threshold:
            break
        next_role    = discord.utils.get(guild.roles, name=next_role_name)
        current_role = discord.utils.get(guild.roles, name=current_role_name)
        if not next_role:
            await channel.send(f"⚠️ الرتبة **{next_role_name}** غير موجودة في السيرفر.")
            break
        try:
            if current_role and current_role in member.roles:
                await member.remove_roles(current_role, reason="ترقية تلقائية")
            await member.add_roles(next_role, reason="ترقية تلقائية")
            embed = discord.Embed(title="🎉 ترقية تلقائية!", color=discord.Color.gold())
            embed.description = (
                f"مبروك {member.mention}! 🥳\n\n"
                f"وصلت إلى **{new_points}** نقطة وتم ترقيتك إلى\n"
                f"✨ **{next_role_name}** ✨"
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        except discord.Forbidden:
            await channel.send("⚠️ البوت لا يملك صلاحية **Manage Roles** لإجراء الترقية.")
        break

# ==================== رتب المشتركين العاديين ====================

RANKS = [
    {"name": "Event Newbie",  "points": 0},
    {"name": "Event Helper",  "points": 100},
    {"name": "Event Legend",  "points": 500},
]

def get_rank_info(points):
    current_rank = RANKS[0]["name"]
    next_rank = None
    points_needed = 0
    for i, rank in enumerate(RANKS):
        if points >= rank["points"]:
            current_rank = rank["name"]
            if i + 1 < len(RANKS):
                next_rank = RANKS[i+1]["name"]
                points_needed = RANKS[i+1]["points"] - points
        else:
            break
    return current_rank, next_rank, points_needed

# ==================== 🚀 تشغيل البوت ====================

@bot.event
async def on_ready():
    print(f'🥳 تم تشغيل البوت بنجاح باسم: {bot.user.name}')

# ==================== 📸 أولاً: حفظ وإرسال الأسئلة ====================

@bot.command()
@staff_only()
async def تصفير_سؤال(ctx, num: int):
    data = load_data()
    if 1 <= num <= 18:
        if str(num) in data["saved_questions"]:
            del data["saved_questions"][str(num)]
            save_data(data)
            await ctx.send(f"✅ تم حذف السؤال رقم {num}.")
        else:
            await ctx.send(f"❌ السؤال رقم {num} غير محفوظ.")
    else:
        await ctx.send("❌ رقم السؤال يجب أن يكون بين 1 و 18.")

@bot.command(name="اسالة")
@staff_only()
async def check_questions(ctx):
    data = load_data()
    saved_list  = [str(i) for i in range(1, 19) if str(i) in data["saved_questions"]]
    missing_list = [str(i) for i in range(1, 19) if str(i) not in data["saved_questions"]]

    embed = discord.Embed(title="📋 حالة الأسئلة المحفوظة", color=discord.Color.blue())
    embed.add_field(
        name=f"✅ محفوظة ({len(saved_list)}/18)",
        value=f"**{' | '.join(saved_list) or 'لا يوجد'}**",
        inline=False
    )
    embed.add_field(
        name=f"❌ غير محفوظة ({len(missing_list)}/18)",
        value=f"**{' | '.join(missing_list) or 'لا يوجد'}**",
        inline=False
    )
    embed.set_footer(text="!حN + صورة لحفظ سؤال | !سN لإرساله")
    await ctx.send(embed=embed)

# ==================== 💎 ثانياً: نقاط طاقم الإيفينت ====================

@bot.command(name="نقاطي")
async def my_points(ctx):
    """يعرض نقاط الإيفينت الخاصة بك (event_points) — متاح للجميع"""
    data = load_data()
    user_id = str(ctx.author.id)
    current_points = data["event_points"].get(user_id, 0)
    user_roles = [role.name for role in ctx.author.roles]

    next_rank = None
    required_points = 0
    if ROLE_TRAINEE in user_roles:
        next_rank, required_points = ROLE_JUNIOR, 15
    elif ROLE_JUNIOR in user_roles:
        next_rank, required_points = ROLE_HELPER, 35
    elif ROLE_HELPER in user_roles:
        next_rank, required_points = ROLE_PROFESSIONAL, 50

    embed = discord.Embed(title="📊 بطاقة نقاط الإيفينت", color=discord.Color.blue())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="✨ نقاطك الحالية:", value=f"`{current_points}` نقطة", inline=False)

    if next_rank:
        if current_points < required_points:
            remaining = required_points - current_points
            status = f"باقي لك `{remaining}` نقطة لتترقى إلى **{next_rank}** 🚀"
        else:
            status = f"جمعت نقاط **{next_rank}** بنجاح! انتظر الترقية 🎉"
    else:
        status = "رتبتك تُرقَّى يدوياً من الإدارة العليا 👑"

    embed.add_field(name="📈 وضع الترقية القادمة:", value=status, inline=False)
    embed.set_footer(text=f"طلب بواسطة: {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="me")
@staff_only()
async def my_stats(ctx):
    """يعرض إحصائياتك من event_points"""
    data = load_data()
    user_id = str(ctx.author.id)
    points = data["event_points"].get(user_id, 0)
    rank, next_rank, points_needed = get_rank_info(points)

    embed = discord.Embed(color=discord.Color.green())
    embed.description = (
        f"⚙️ **ملف الإحصائيات الشخصي**\n\n"
        f"**العضو 👤**\n{ctx.author.mention}\n\n"
        f"**النقاط الحالية 💎**\n{points}\n\n"
        f"**الرتبة الحالية 🎖️**\n{rank}\n\n"
        f"**التقدم 📈**\n"
        + (f"باقي {points_needed} نقطة للوصول إلى **{next_rank}**" if next_rank else "وصلت لأعلى رتبة! 🔥")
    )
    await ctx.send(embed=embed)

# لوحة صدارة طاقم الإيفينت (event_points)
@bot.command(name="النقاط")
@staff_only()
async def leaderboard_event(ctx):
    data = load_data()
    if not data["event_points"]:
        await ctx.send("📋 لوحة صدارة الإيفينت فارغة حالياً.")
        return

    sorted_users = sorted(data["event_points"].items(), key=lambda x: x[1], reverse=True)
    embed = discord.Embed(title="🏆 لوحة صدارة نقاط الإيفينت 🏆", color=discord.Color.gold())

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (user_id, points) in enumerate(sorted_users[:10]):
        member = ctx.guild.get_member(int(user_id))
        user_name = member.mention if member else f"عضو غادر ({user_id})"
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        lines.append(f"{medal} {user_name} — **{points}** نقطة")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"إجمالي الأعضاء: {len(data['event_points'])}")
    await ctx.send(embed=embed)

# ==================== 👥 ثالثاً: نقاط المشتركين العاديين ====================

# لوحة صدارة المشتركين العاديين (regular_points)
@bot.command(name="ترتيب")
@staff_only()
async def leaderboard_members(ctx):
    data = load_data()
    if not data["regular_points"]:
        await ctx.send("📋 لوحة صدارة الأعضاء فارغة حالياً، لا توجد نقاط مسجلة.")
        return

    sorted_users = sorted(data["regular_points"].items(), key=lambda x: x[1], reverse=True)
    embed = discord.Embed(title="🏆 لوحة صدارة الأعضاء والمشتركين 🏆", color=discord.Color.green())

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (user_id, points) in enumerate(sorted_users[:10]):
        member = ctx.guild.get_member(int(user_id))
        user_name = member.mention if member else f"مستخدم غادر ({user_id})"
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        lines.append(f"{medal} {user_name} — **{points}** نقطة")

    embed.description = "\n".join(lines)
    embed.set_footer(text=f"إجمالي المشتركين: {len(data['regular_points'])}")
    await ctx.send(embed=embed)

# ==================== 🎉 رابعاً: السحب العشوائي ====================

@bot.command(name="سحب")
@staff_only()
async def draw_winner(ctx):
    """يجد المتعادلين في أعلى نقاط الإيفينت ويختار واحداً عشوائياً"""
    data = load_data()
    if not data["regular_points"]:
        await ctx.send("❌ لا توجد نقاط إيفينت مسجلة لإجراء السحب.")
        return

    # إيجاد أعلى نقاط
    max_points = max(data["regular_points"].values())

    # إيجاد جميع المتعادلين عند أعلى نقاط
    tied = [uid for uid, pts in data["regular_points"].items() if pts == max_points]

    # اختيار فائز عشوائي
    winner_id = random.choice(tied)
    winner_member = ctx.guild.get_member(int(winner_id))
    winner_name = winner_member.mention if winner_member else f"عضو ({winner_id})"

    embed = discord.Embed(title="🎉 نتيجة السحب العشوائي 🎉", color=discord.Color.gold())

    if len(tied) > 1:
        tied_names = []
        for uid in tied:
            m = ctx.guild.get_member(int(uid))
            tied_names.append(m.mention if m else f"({uid})")
        embed.add_field(
            name=f"⚖️ المتعادلون ({len(tied)} أعضاء)",
            value=" | ".join(tied_names),
            inline=False
        )
    embed.add_field(name="🏆 الفائز", value=winner_name, inline=False)
    embed.add_field(name="💎 النقاط", value=f"{max_points} نقطة", inline=False)
    embed.add_field(name="👥 إجمالي المشاركين", value=f"{len(data['event_points'])} عضو", inline=False)
    embed.set_footer(text=f"السحب بواسطة: {ctx.author.name}")
    await ctx.send(embed=embed)

# ==================== 🛡️ خامساً: التحكم الإداري بالنقاط ====================

def _build_event_card(member: discord.Member, points: int, footer_text: str, title: str = "💎 بطاقة نقاط الإيفينت") -> discord.Embed:
    """ينشئ بطاقة نقاط إيفينت لعضو معين"""
    member_roles = [role.name for role in member.roles]
    next_rank = None
    required_points = 0
    if ROLE_TRAINEE in member_roles:
        next_rank, required_points = ROLE_JUNIOR, 15
    elif ROLE_JUNIOR in member_roles:
        next_rank, required_points = ROLE_HELPER, 35
    elif ROLE_HELPER in member_roles:
        next_rank, required_points = ROLE_PROFESSIONAL, 50

    if next_rank:
        if points < required_points:
            remaining = required_points - points
            progress = f"باقي `{remaining}` نقطة للوصول إلى **{next_rank}** 🚀"
        else:
            progress = f"جمع نقاط **{next_rank}** بنجاح! انتظر الترقية 🎉"
    else:
        progress = "في رتبة تُرقَّى يدوياً من الإدارة العليا 👑"

    embed = discord.Embed(color=discord.Color.blue())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.description = (
        f"{title}\n\n"
        f"**العضو 👤**\n{member.mention}\n\n"
        f"**النقاط الحالية 💎**\n{points} نقطة\n\n"
        f"**التقدم 📈**\n{progress}"
    )
    embed.set_footer(text=footer_text)
    return embed

@bot.command(name="نقاط")
@points_admin_only()
async def add_points(ctx, member: discord.Member, amount: int = None):
    """
    !نقاط @عضو        ← عرض بطاقة نقاط العضو (للإدارة فقط)
    !نقاط @عضو [عدد]  ← إضافة أو خصم نقاط الإيفينت
    """
    data = load_data()
    user_id = str(member.id)
    current_points = data["event_points"].get(user_id, 0)

    # ─── وضع العرض فقط (بدون رقم) ───
    if amount is None:
        embed = _build_event_card(
            member, current_points,
            footer_text=f"استعلام بواسطة: {ctx.author.name}"
        )
        await ctx.send(embed=embed)
        return

    # ─── وضع الإضافة / الخصم ───
    new_points = max(0, current_points + amount)
    data["event_points"][user_id] = new_points
    save_data(data)

    sign   = "+" if amount >= 0 else ""
    action = "إضافة" if amount >= 0 else "خصم"

    embed = discord.Embed(color=discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)

    member_roles = [role.name for role in member.roles]
    next_rank = None
    required_points = 0
    if ROLE_TRAINEE in member_roles:
        next_rank, required_points = ROLE_JUNIOR, 15
    elif ROLE_JUNIOR in member_roles:
        next_rank, required_points = ROLE_HELPER, 35
    elif ROLE_HELPER in member_roles:
        next_rank, required_points = ROLE_PROFESSIONAL, 50

    if next_rank:
        if new_points < required_points:
            progress = f"باقي `{required_points - new_points}` نقطة للوصول إلى **{next_rank}** 🚀"
        else:
            progress = f"جمع نقاط **{next_rank}** بنجاح! انتظر الترقية 🎉"
    else:
        progress = "في رتبة تُرقَّى يدوياً من الإدارة العليا 👑"

    embed.description = (
        f"💎 **تحديث نقاط الإيفينت**\n\n"
        f"**العضو 👤**\n{member.mention}\n\n"
        f"**العملية**\n{action} `{sign}{amount}` نقطة\n\n"
        f"**النقاط الحالية 💎**\n{new_points} نقطة\n\n"
        f"**التقدم 📈**\n{progress}"
    )
    embed.set_footer(text=f"بواسطة: {ctx.author.name}")
    await ctx.send(embed=embed)
    await auto_promote(member, new_points, ctx.channel)

@bot.command(name="ن")
@staff_only()
async def manage_member_points(ctx, member: discord.Member, amount: int):
    """اختصار لإضافة/خصم نقاط الإيفينت مع أزرار"""
    data = load_data()
    user_id = str(member.id)

    status = "تم إضافة النقاط بنجاح ✅" if amount >= 0 else "تم خصم النقاط بنجاح ❌"
    sign   = "+" if amount >= 0 else ""

    old_points = data["event_points"].get(user_id, 0)
    new_points = max(0, old_points + amount)
    data["event_points"][user_id] = new_points
    save_data(data)

    rank, next_rank, points_needed = get_rank_info(new_points)
    embed = discord.Embed(color=discord.Color.green())
    embed.description = (
        f"⚙️ **إدارة نقاط الأعضاء**\n\n"
        f"**الحالة**\n{status}\n\n"
        f"**العضو 👤**\n{member.mention}\n\n"
        f"**النقاط الحالية 💎**\n{new_points}\n\n"
        f"**المقدار**\n{sign}{amount}\n\n"
        f"**التقدم 📈**\n"
        + (f"باقي {points_needed} نقطة للوصول إلى **{next_rank}**" if next_rank else "أعلى رتبة! 🔥")
    )

    view = View()
    view.add_item(Button(label="إضافة", style=discord.ButtonStyle.green, custom_id="add_btn"))
    view.add_item(Button(label="خصم", style=discord.ButtonStyle.red, custom_id="sub_btn"))
    view.add_item(Button(label="تعيين", style=discord.ButtonStyle.blurple, custom_id="set_btn"))
    await ctx.send(embed=embed, view=view)

@bot.command(name="p")
@staff_only()
async def manage_staff_points(ctx, member: discord.Member, amount: int):
    """يضيف أو يخصم نقاط إدارية (staff_points)"""
    data = load_data()
    user_id = str(member.id)
    data["staff_points"][user_id] = data["staff_points"].get(user_id, 0) + amount
    save_data(data)
    action = "إضافة" if amount >= 0 else "خصم"
    await ctx.send(
        f"✅ تم {action} `{abs(amount)}` نقاط إدارية للمنظم {member.mention}. "
        f"المجموع: {data['staff_points'][user_id]}"
    )

@bot.command(name="تصفير")
@staff_only()
async def reset_all_points(ctx):
    """يصفّر جميع نقاط الإيفينت (event_points)"""
    data = load_data()
    data["event_points"].clear()
    save_data(data)
    await ctx.send("🔄 تم تصفير جميع نقاط الإيفينت بنجاح!")

# ==================== ⚙️ سادساً: الأحداث التلقائية ====================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    data = load_data()

    # !حN + صورة → حفظ سؤال
    if content.startswith('!ح'):
        if not is_staff_member(message.author):
            return
        try:
            num = int(content[2:])
            if 1 <= num <= 18:
                if message.attachments:
                    data["saved_questions"][str(num)] = message.attachments[0].url
                    save_data(data)
                    await message.channel.send(f"✅ تم حفظ الصورة كـ سؤال رقم {num}!")
                else:
                    await message.channel.send("❌ أرفق صورة مع الأمر.")
        except ValueError:
            pass

    # !سN → إرسال سؤال بعداد تنازلي
    elif content.startswith('!س'):
        if not is_staff_member(message.author):
            return
        try:
            num = int(content[2:])
            if 1 <= num <= 18:
                if str(num) in data["saved_questions"]:
                    for count in ["1 🔥", "2 🔥", "3 🔥"]:
                        await message.channel.send(count)
                        await asyncio.sleep(1)
                    embed = discord.Embed(
                        title="🏁 انطلقوووا!!! ما هي الإجابة؟",
                        color=discord.Color.purple()
                    )
                    embed.set_image(url=data["saved_questions"][str(num)])
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send(
                        f"❌ السؤال رقم {num} غير محفوظ، ارفع صورته مع `!ح{num}` أولاً."
                    )
        except ValueError:
            pass

    await bot.process_commands(message)

def is_staff_member(member):
    """تحقق من صلاحية العضو في on_message (بدون ctx)"""
    try:
        if member.guild_permissions.administrator:
            return True
        member_roles = [role.name.lower().strip() for role in member.roles]
        return any(r.lower().strip() in member_roles for r in STAFF_ROLES)
    except Exception:
        return False

# تفاعل ✅ → نقطة لصاحب الرسالة في regular_points
@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != "✅":
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    reactor = guild.get_member(payload.user_id)
    if not reactor or reactor.bot:
        return

    

    channel = bot.get_channel(payload.channel_id)
    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    author = message.author


    data = load_data()
    user_id = str(author.id)
    data["regular_points"][user_id] = data["regular_points"].get(user_id, 0) + 1
    new_points = data["regular_points"][user_id]
    save_data(data)

    await channel.send(f"تم إضافة نقطة لـ {author.mention} ✅ المجموع: {new_points}")

# ==================== 📋 سابعاً: قائمة الأوامر ====================

@bot.command(name="اوامر")
@staff_only()
async def show_help(ctx):
    embed = discord.Embed(
        title="⚙️ قائمة أوامر System ESD",
        description="جميع الأوامر المبرمجة في البوت مصنّفة حسب النوع:",
        color=discord.Color.red()
    )

    embed.add_field(
        name="📸 أوامر الأسئلة — طاقم الإيفينت",
        value=(
            "`!حN` + صورة\n"
            "حفظ صورة السؤال رقم N (1-18).\n\n"
            "`!سN`\n"
            "إرسال السؤال رقم N مع عداد تنازلي.\n\n"
            "`!اسالة`\n"
            "عرض الأسئلة المحفوظة والناقصة (1-18).\n\n"
            "`!تصفير_سؤال [رقم]`\n"
            "حذف سؤال محدد لإعادة حفظه."
        ),
        inline=False
    )

    embed.add_field(
        name="💎 أوامر نقاط الإيفينت — الإدارة العليا + Permission",
        value=(
            "`!نقاط @عضو [عدد]`\n"
            "إضافة أو خصم نقاط الإيفينت لعضو محدد.\n"
            "الصلاحية: Permission / E.S.D CEO / Owner / Co-Owner / Founder / Manager\n\n"
            "`!ن @عضو [عدد]`\n"
            "نفس وظيفة !نقاط مع أزرار تفاعلية (طاقم الإيفينت).\n\n"
            "`!النقاط`\n"
            "لوحة صدارة أعلى 10 في نقاط الإيفينت.\n\n"
            "`!تصفير`\n"
            "تصفير جميع نقاط الإيفينت الحالي."
        ),
        inline=False
    )

    embed.add_field(
        name="👥 أوامر المشتركين العاديين",
        value=(
            "`!نقاطي`\n"
            "يعرض نقاط الإيفينت الخاصة بك ووضع ترقيتك — متاح للجميع.\n\n"
            "`!me`\n"
            "عرض إحصائياتك الكاملة (طاقم الإيفينت).\n\n"
            "`!ترتيب`\n"
            "لوحة صدارة المشتركين العاديين (نقاط التفاعل بـ ✅).\n\n"
            "تفاعل ✅ على رسالة عضو\n"
            "يضيف نقطة تلقائياً للعضو في لوحة !ترتيب."
        ),
        inline=False
    )

    embed.add_field(
        name="🎉 السحب العشوائي — طاقم الإيفينت",
        value=(
            "`!سحب`\n"
            "يجد المتعادلين عند أعلى نقاط الإيفينت ويختار فائزاً عشوائياً.\n"
            "إذا كان هناك فائز واحد في المقدمة يُعلن مباشرة."
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ الأوامر الإدارية — طاقم الإيفينت",
        value=(
            "`!p @عضو [عدد]`\n"
            "إضافة أو خصم نقاط إدارية (staff_points) للمنظمين."
        ),
        inline=False
    )
    import os
bot.run(os.getenv("DISCORD_TOKEN"))


