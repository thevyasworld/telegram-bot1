import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError
from datetime import datetime
import asyncio
import re

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "7557701698:AAG3ipeIVpFXxv8amQ5Z-ipJZDlmhf4ZnDo"  # Replace with your actual bot token
ADMIN_USER_ID = 6214327363 
CHANNEL_ID = "@thevyasworld"  # Replace with your channel username (with @) or channel ID
CHANNEL_INVITE_LINK = "https://t.me/thevyasworld"  # Replace with your channel invite link

# Store file information
uploaded_files = {}
user_stats = {}
file_id_mapping = {}  # Map short IDs to actual file IDs
user_searches = {}  # Store user search queries
file_categories = {}  # Store file categories
next_file_id = 1

# Common file categories
CATEGORIES = {
    'document': ['pdf', 'doc', 'docx', 'txt', 'rtf'],
    'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg'],
    'video': ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv'],
    'audio': ['mp3', 'wav', 'flac', 'aac', 'ogg'],
    'archive': ['zip', 'rar', '7z', 'tar', 'gz'],
    'code': ['py', 'js', 'html', 'css', 'java', 'cpp', 'c'],
    'other': []
}

class TelegramBot:
    def __init__(self):
        self.application = None
    
    def get_file_category(self, filename):
        """Determine file category based on extension"""
        if not filename:
            return 'other'
        
        extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        for category, extensions in CATEGORIES.items():
            if extension in extensions:
                return category
        return 'other'
    
    def search_files(self, query, user_id=None):
        """Search files by name or category"""
        if not query:
            return {}
        
        query = query.lower().strip()
        active_files = {fid: info for fid, info in uploaded_files.items() if info.get('active', False)}
        
        # Search by filename
        filename_matches = {}
        for fid, info in active_files.items():
            if query in info['name'].lower():
                filename_matches[fid] = info
        
        # Search by category
        category_matches = {}
        for fid, info in active_files.items():
            file_category = self.get_file_category(info['name'])
            if query in file_category or query in info['name'].lower():
                category_matches[fid] = info
        
        # Combine and prioritize exact matches
        results = {}
        # First add exact filename matches
        for fid, info in filename_matches.items():
            results[fid] = info
        # Then add category matches that aren't already included
        for fid, info in category_matches.items():
            if fid not in results:
                results[fid] = info
        
        return results
    
    async def check_channel_membership(self, user_id: int) -> bool:
        """Check if user is a member of the required channel"""
        try:
            member = await self.application.bot.get_chat_member(CHANNEL_ID, user_id)
            return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
        except TelegramError as e:
            logger.error(f"Error checking channel membership: {e}")
            return False
    
    async def membership_required(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Decorator-like function to check membership before allowing access"""
        user_id = update.effective_user.id
        
        # Admin bypass
        if user_id == ADMIN_USER_ID:
            return True
            
        is_member = await self.check_channel_membership(user_id)
        
        if not is_member:
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_INVITE_LINK)],
                [InlineKeyboardButton("✅ I Joined", callback_data="check_membership")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            join_message = f"""
🔒 **Access Restricted**

To access files and features, you must join our channel first!

📢 **Why join?**
• Get latest updates
• Access exclusive content
• Be part of our community

👆 Click "Join Channel" above, then click "I Joined" to verify!
            """
            
            if update.message:
                await update.message.reply_text(join_message, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(join_message, reply_markup=reply_markup)
            
            return False
        
        return True
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        user_id = user.id
        
        # Check channel membership first
        if not await self.membership_required(update, context):
            return
        
        # Initialize user stats
        if user_id not in user_stats:
            user_stats[user_id] = {
                'downloads': 0,
                'join_date': datetime.now().strftime('%Y-%m-%d'),
                'last_active': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
        
        welcome_text = f"""
🎉 Welcome {user.first_name}! 

✅ **Channel membership verified!**

🤖 I'm your exclusive file sharing bot!

📁 **Available Commands:**
/start - Show this menu
/files - View all files
/search - Search for files
/categories - Browse by category
/stats - Your usage statistics
/help - Get help

🔍 **New Features:**
• Search files by name
• Examples- /search filename.zip
=>Filename is to be on youtube channel(TheVyas World)
Click the buttons below to explore! 👇
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 All Files", callback_data="view_files"),
             InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
            [InlineKeyboardButton("📂 Categories", callback_data="view_categories"),
             InlineKeyboardButton("📊 My Stats", callback_data="user_stats")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle search command"""
        # Check channel membership
        if not await self.membership_required(update, context):
            return
        
        # Get search query from command args
        query = ' '.join(context.args) if context.args else ''
        
        if not query:
            await update.message.reply_text(
                "🔍 **Search Files**\n\n"
                "📝 **How to search:**\n"
                "• `/search filename` - Search by filename\n"
                "💡 **Tip:** Use the Search button for interactive search!"
            )
            return
        
        user_id = update.effective_user.id
        results = self.search_files(query, user_id)
        
        if not results:
            keyboard = [
                [InlineKeyboardButton("🔍 Try Another Search", callback_data="search_prompt")],
                [InlineKeyboardButton("📁 View All Files", callback_data="view_files")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🔍 **Search Results for '{query}'**\n\n"
                f"❌ No files found matching your search.\n\n"
                f"💡 **Tips:**\n"
                f"• Try different keywords\n"
                f"• Search by file type (pdf, video, etc.)\n"
                f"• Use /files to see all available files",
                reply_markup=reply_markup
            )
            return
        
        # Store search query for user
        user_searches[user_id] = query
        
        keyboard = []
        results_text = f"🔍 **Search Results for '{query}'**\n\n"
        results_text += f"📁 **Found {len(results)} files:**\n\n"
        
        for short_id, file_info in list(results.items())[:10]:  # Limit to 10 results
            results_text += f"📄 **{file_info['name']}**\n"
            results_text += f"   📏 {self.format_file_size(file_info['size'])} | ⬇️ {file_info['downloads']} downloads\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⬇️ {file_info['name'][:25]}{'...' if len(file_info['name']) > 25 else ''}", 
                callback_data=f"dl_{short_id}"
            )])
        
        if len(results) > 10:
            results_text += f"... and {len(results) - 10} more results\n\n"
            keyboard.append([InlineKeyboardButton("📋 Show All Results", callback_data=f"search_all_{query}")])
        
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_prompt")])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(results_text, reply_markup=reply_markup)
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages for search"""
        user_id = update.effective_user.id
        message_text=update.message.text.strip()

        if user_id in user_searches and user_searches[user_id].startswith("WAITING_FOR_YOUTUBE_"):
            short_id = user_searches[user_id].replace("WAITING_FOR_YOUTUBE_", "")
        
            if short_id in uploaded_files:
                if message_text.lower() == 'remove':
                   uploaded_files[short_id]['youtube_link'] = None
                   link_status = "🗑️ YouTube link removed"
                else:
                # Basic YouTube URL validation
                    if 'youtube.com' in message_text or 'youtu.be' in message_text:
                        uploaded_files[short_id]['youtube_link'] = message_text
                        link_status = "✅ YouTube link added"
                    else:
                        await update.message.reply_text("❌ Please send a valid YouTube link!")
                        return
                    
                del user_searches[user_id]
            
            keyboard = [
                [InlineKeyboardButton("✅ Make Available", callback_data=f"approve_{short_id}")],
                [InlineKeyboardButton("🔗 Change YouTube Link", callback_data=f"youtube_{short_id}")],
                [InlineKeyboardButton("🏷️ Change Category", callback_data=f"category_{short_id}")],
                [InlineKeyboardButton("❌ Delete", callback_data=f"delete_{short_id}")],
                [InlineKeyboardButton("📊 File Stats", callback_data=f"stats_{short_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{link_status}\n\n"
                f"📁 **{uploaded_files[short_id]['name']}**\n"
                f"🔗 Link: {uploaded_files[short_id].get('youtube_link', 'None')}\n\n"
                f"🔧 **Admin Actions:**",
                reply_markup=reply_markup
            )
        return
        
        # Check if user is in search mode
        if user_id in user_searches and user_searches[user_id] == "WAITING_FOR_SEARCH":
            query = update.message.text.strip()
            user_searches[user_id] = query
            
            results = self.search_files(query, user_id)
            
            if not results:
                keyboard = [
                    [InlineKeyboardButton("🔍 Try Again", callback_data="search_prompt")],
                    [InlineKeyboardButton("📁 All Files", callback_data="view_files")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"🔍 **Search Results for '{query}'**\n\n"
                    f"❌ No files found matching your search.\n\n"
                    f"💡 **Try:**\n"
                    f"• Different keywords\n"
                    f"• File extensions (pdf, mp4, etc.)\n"
                    f"• Categories (document, video, etc.)",
                    reply_markup=reply_markup
                )
                return
            
            await self.show_search_results(update.message, query, results)
    
    async def show_search_results(self, message, query, results):
        """Show search results"""
        keyboard = []
        results_text = f"🔍 **Search: '{query}'**\n\n"
        results_text += f"📁 **Found {len(results)} files:**\n\n"
        
        for short_id, file_info in list(results.items())[:8]:  # Limit to 8 for better display
            results_text += f"📄 **{file_info['name']}**\n"
            results_text += f"   📏 {self.format_file_size(file_info['size'])} | ⬇️ {file_info['downloads']} downloads\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⬇️ {file_info['name'][:30]}{'...' if len(file_info['name']) > 30 else ''}", 
                callback_data=f"dl_{short_id}"
            )])
        
        if len(results) > 8:
            results_text += f"... and {len(results) - 8} more results\n\n"
        
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_prompt")])
        keyboard.append([InlineKeyboardButton("📂 Categories", callback_data="view_categories")])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(results_text, reply_markup=reply_markup)
    
    async def handle_file_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads from admin"""
        global next_file_id
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("❌ Only admin can upload files!")
            return
        
        if update.message.document:
            file = update.message.document
            file_id = file.file_id
            file_name = file.file_name
            file_size = file.file_size
            
            # Create short ID for callback data
            short_id = str(next_file_id)
            next_file_id += 1
            
            # Store mapping
            file_id_mapping[short_id] = file_id
            
            # Determine category
            category = self.get_file_category(file_name)
            
            # Store file information
            uploaded_files[short_id] = {
                'name': file_name,
                'size': file_size,
                'category': category,
                'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'downloads': 0,
                'active': False,  # File needs approval
                'telegram_file_id': file_id,
                'youtube_link':None
            }
            
            keyboard = [
                [InlineKeyboardButton("✅ Make Available", callback_data=f"approve_{short_id}")],
                [InlineKeyboardButton("🔗 Add YouTube Link", callback_data=f"youtube_{short_id}")],
                [InlineKeyboardButton("🏷️ Change Category", callback_data=f"category_{short_id}")],
                [InlineKeyboardButton("❌ Delete", callback_data=f"delete_{short_id}")],
                [InlineKeyboardButton("📊 File Stats", callback_data=f"stats_{short_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📁 **File Uploaded Successfully!**\n\n"
                f"📄 Name: `{file_name}`\n"
                f"📏 Size: {self.format_file_size(file_size)}\n"
                f"🏷️ Category: {category.title()}\n"
                f"📅 Uploaded: {uploaded_files[short_id]['upload_date']}\n\n"
                f"🔧 **Admin Actions:**",
                reply_markup=reply_markup
            )
    
    async def files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available files"""
        # Check channel membership
        if not await self.membership_required(update, context):
            return
        
        await self.show_files_with_pagination(update.message, page=1)
    
    async def show_files_with_pagination(self, message, page=1, files_per_page=5):
        """Show files with pagination"""
        active_files = {fid: info for fid, info in uploaded_files.items() if info.get('active', False)}
        
        if not active_files:
            keyboard = [
                [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(
                "📭 **No files available yet!**\n\n"
                "Check back later for new uploads! 🔄",
                reply_markup=reply_markup
            )
            return
        
        # Calculate pagination
        total_files = len(active_files)
        total_pages = (total_files - 1) // files_per_page + 1
        start_idx = (page - 1) * files_per_page
        end_idx = start_idx + files_per_page
        
        file_items = list(active_files.items())[start_idx:end_idx]
        
        keyboard = []
        files_text = f"📁 **All Files (Page {page}/{total_pages})**\n\n"
        files_text += f"📊 **Total: {total_files} files**\n\n"
        
        for short_id, file_info in file_items:
            files_text += f"📄 **{file_info['name']}**\n"
            files_text += f"   📏 {self.format_file_size(file_info['size'])} | 🏷️ {file_info.get('category', 'other').title()}\n"
            files_text += f"   ⬇️ {file_info['downloads']} downloads | 📅 {file_info['upload_date']}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⬇️ {file_info['name'][:30]}{'...' if len(file_info['name']) > 30 else ''}", 
                callback_data=f"dl_{short_id}"
            )])
        
        # Pagination buttons
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Action buttons
        keyboard.append([
            InlineKeyboardButton("🔍 Search", callback_data="search_prompt"),
            InlineKeyboardButton("📂 Categories", callback_data="view_categories")
        ])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(files_text, reply_markup=reply_markup)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user statistics"""
        # Check channel membership
        if not await self.membership_required(update, context):
            return
            
        user_id = update.effective_user.id
        user = update.effective_user
        
        if user_id not in user_stats:
            user_stats[user_id] = {
                'downloads': 0,
                'join_date': datetime.now().strftime('%Y-%m-%d'),
                'last_active': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
        
        stats = user_stats[user_id]
        stats['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        active_files_count = len([f for f in uploaded_files.values() if f.get('active', False)])
        
        # Category breakdown
        category_counts = {}
        for file_info in uploaded_files.values():
            if file_info.get('active', False):
                category = file_info.get('category', 'other')
                category_counts[category] = category_counts.get(category, 0) + 1
        
        stats_text = f"""
📊 **Your Statistics**

👤 **User Info:**
   Name: {user.first_name}
   Status: ✅ Channel Member

📈 **Activity:**
   📅 Member Since: {stats['join_date']}
   ⬇️ Total Downloads: {stats['downloads']}
   🕐 Last Active: {stats['last_active']}

📁 **Available Content:**
   Total Files: {active_files_count}
   Total Downloads: {sum(f['downloads'] for f in uploaded_files.values())}

📂 **Categories:**
        """
        
        for category, count in category_counts.items():
            stats_text += f"   {category.title()}: {count} files\n"
        
        keyboard = [
            [InlineKeyboardButton("📁 View Files", callback_data="view_files")],
            [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data="user_stats")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        # Check channel membership
        if not await self.membership_required(update, context):
            return
            
        help_text = f"""
❓ **Help & Guide**

🔐 **Access Requirements:**
✅ Must be a member of {CHANNEL_ID}
✅ Use bot commands to interact

📋 **Available Commands:**
• `/start` - Main menu & welcome
• `/files` - Browse all files
• `/search [query]` - Search for files
• `/categories` - Browse by category
• `/stats` - Your usage statistics
• `/help` - This help message

🔍 **Search Features:**
• Search by filename
• Search by file type (pdf, mp4, etc.)
• Search by category
• Interactive search prompts

🎯 **How to Use:**
1️⃣ Browse files or search for specific ones
2️⃣ Click download buttons
3️⃣ Files sent directly to you
4️⃣ Check stats anytime

🔧 **Features:**
✅ Advanced search functionality
✅ File categorization
✅ Pagination for large file lists
✅ Channel membership verification
✅ Download tracking
✅ User statistics
✅ Interactive buttons

📢 **Stay Updated:**
Make sure to stay in {CHANNEL_ID} for continued access!

❓ **Need Help?**
Contact the admin for support!
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 Browse Files", callback_data="view_files")],
            [InlineKeyboardButton("🔍 Search Files", callback_data="search_prompt")],
            [InlineKeyboardButton("📢 Visit Channel", url=CHANNEL_INVITE_LINK)],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(help_text, reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data
        
        await query.answer()
        
        # Handle membership check
        if data == "check_membership":
            is_member = await self.check_channel_membership(user_id)
            if is_member:
                await query.edit_message_text(
                    "✅ **Membership Verified!**\n\n"
                    "Welcome! You now have access to all features.\n"
                    "Use /start to begin!"
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("✅ I Joined", callback_data="check_membership")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "❌ **Not a member yet!**\n\n"
                    "Please join the channel first, then click 'I Joined'.",
                    reply_markup=reply_markup
                )
            return
        
        # Check membership for all other actions
        if user_id != ADMIN_USER_ID:
            if not await self.check_channel_membership(user_id):
                keyboard = [
                    [InlineKeyboardButton("📢 Join Channel", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("✅ I Joined", callback_data="check_membership")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "🔒 **Channel membership required!**\n\n"
                    "Please join our channel to continue using the bot.",
                    reply_markup=reply_markup
                )
                return
        
        # Update user activity
        if user_id in user_stats:
            user_stats[user_id]['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # Handle different callback actions
        if data == "view_files":
            await self.show_files_inline(query)
        elif data == "search_prompt":
            await self.show_search_prompt(query)
        elif data == "view_categories":
            await self.show_categories(query)
        elif data == "user_stats":
            await self.show_stats_inline(query)
        elif data == "help":
            await self.show_help_inline(query)
        elif data == "main_menu":
            await self.show_main_menu_inline(query)
        elif data.startswith("youtube_"):
            await self.handle_youtube_link(query,data)
        elif data.startswith("page_"):
            page = int(data.replace("page_", ""))
            await self.show_files_inline_paginated(query, page)
        
        elif data.startswith("category_"):
            if data.startswith("category_view_"):
                category = data.replace("category_view_", "")
                await self.show_category_files(query, category)
            else:
                # Admin category change
                await self.handle_category_change(query, data)
        elif data.startswith("dl_"):
            await self.handle_download(query, data)
        elif data.startswith("approve_"):
            await self.handle_approve(query, data)
        elif data.startswith("delete_"):
            await self.handle_delete(query, data)
        elif data.startswith("stats_"):
            await self.handle_file_stats(query, data)
    
    async def show_search_prompt(self, query):
        """Show search prompt"""
        user_id = query.from_user.id
        user_searches[user_id] = "WAITING_FOR_SEARCH"
        
        search_text = """
🔍 **Search Files**

💬 **Type your search query:**
• Filename: `report`, `video`, `2024`
• File type: `pdf`, `mp4`, `jpg`
• Category: `document`, `video`, `image`

🎯 **Examples:**
• `python tutorial` - Find Python tutorials
• `pdf` - Find all PDF files
• `video` - Find all video files

📝 **Just type your search and I'll find matching files!**
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 Browse All Files", callback_data="view_files")],
            [InlineKeyboardButton("📂 Browse Categories", callback_data="view_categories")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(search_text, reply_markup=reply_markup)
    
    async def show_categories(self, query):
        """Show file categories"""
        active_files = {fid: info for fid, info in uploaded_files.items() if info.get('active', False)}
        
        # Count files per category
        category_counts = {}
        for file_info in active_files.values():
            category = file_info.get('category', 'other')
            category_counts[category] = category_counts.get(category, 0) + 1
        
        if not category_counts:
            keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📂 **No files available yet!**\n\n"
                "Check back later for new uploads! 🔄",
                reply_markup=reply_markup
            )
            return
        
        categories_text = "📂 **Browse by Category**\n\n"
        keyboard = []
        
        # Category icons
        category_icons = {
            'document': '📄',
            'image': '🖼️',
            'video': '🎥',
            'audio': '🎵',
            'archive': '📦',
            'code': '💻',
            'other': '📁'
        }
        
        for category, count in category_counts.items():
            icon = category_icons.get(category, '📁')
            categories_text += f"{icon} **{category.title()}** - {count} files\n"
            
            keyboard.append([InlineKeyboardButton(
                f"{icon} {category.title()} ({count})",
                callback_data=f"category_view_{category}"
            )])
        
        keyboard.append([InlineKeyboardButton("📁 All Files", callback_data="view_files")])
        keyboard.append([InlineKeyboardButton("🔍 Search", callback_data="search_prompt")])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(categories_text, reply_markup=reply_markup)
    
    async def show_category_files(self, query, category):
        """Show files in a specific category"""
        active_files = {fid: info for fid, info in uploaded_files.items() 
                       if info.get('active', False) and info.get('category', 'other') == category}
        
        if not active_files:
            keyboard = [
                [InlineKeyboardButton("📂 Back to Categories", callback_data="view_categories")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📂 **{category.title()} Category**\n\n"
                f"❌ No {category} files available yet!",
                reply_markup=reply_markup
            )
            return
        
        category_icons = {
            'document': '📄',
            'image': '🖼️',
            'video': '🎥',
            'audio': '🎵',
            'archive': '📦',
            'code': '💻',
            'other': '📁'
        }
        
        icon = category_icons.get(category, '📁')
        
        keyboard = []
        files_text = f"{icon} **{category.title()} Files**\n\n"
        files_text += f"📊 **{len(active_files)} files in this category:**\n\n"
        
        for short_id, file_info in list(active_files.items())[:8]:  # Limit to 8 files
            files_text += f"📄 **{file_info['name']}**\n"
            files_text += f"   📏 {self.format_file_size(file_info['size'])} | ⬇️ {file_info['downloads']} downloads\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⬇️ {file_info['name'][:30]}{'...' if len(file_info['name']) > 30 else ''}", 
                callback_data=f"dl_{short_id}"
            )])
        
        if len(active_files) > 8:
            files_text += f"... and {len(active_files) - 8} more files in this category\n\n"
        
        keyboard.append([InlineKeyboardButton("📂 Back to Categories", callback_data="view_categories")])
        keyboard.append([InlineKeyboardButton("📁 All Files", callback_data="view_files")])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(files_text, reply_markup=reply_markup)
    
    async def show_files_inline(self, query):
        """Show files in inline message"""
        await self.show_files_inline_paginated(query, 1)
    
    async def show_files_inline_paginated(self, query, page=1, files_per_page=5):
        """Show files with pagination in inline message"""
        active_files = {fid: info for fid, info in uploaded_files.items() if info.get('active', False)}
        
        if not active_files:
            keyboard = [
                [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📭 **No files available yet!**\n\n"
                "Check back later for new uploads! 🔄",
                reply_markup=reply_markup
            )
            return
        
        # Calculate pagination
        total_files = len(active_files)
        total_pages = (total_files - 1) // files_per_page + 1
        start_idx = (page - 1) * files_per_page
        end_idx = start_idx + files_per_page
        
        file_items = list(active_files.items())[start_idx:end_idx]
        
        keyboard = []
        files_text = f"📁 **All Files (Page {page}/{total_pages})**\n\n"
        files_text += f"📊 **Total: {total_files} files**\n\n"
        
        for short_id, file_info in file_items:
            files_text += f"📄 **{file_info['name']}**\n"
            files_text += f"   📏 {self.format_file_size(file_info['size'])} | 🏷️ {file_info.get('category', 'other').title()}\n"
            files_text += f"   ⬇️ {file_info['downloads']} downloads\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⬇️ {file_info['name'][:30]}{'...' if len(file_info['name']) > 30 else ''}", 
                callback_data=f"dl_{short_id}"
            )])
        
        # Pagination buttons
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Action buttons
        keyboard.append([
            InlineKeyboardButton("🔍 Search", callback_data="search_prompt"),
            InlineKeyboardButton("📂 Categories", callback_data="view_categories")
        ])
        keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(files_text, reply_markup=reply_markup)
    
    async def show_stats_inline(self, query):
        """Show user stats in inline message"""
        user_id = query.from_user.id
        user = query.from_user
        
        if user_id not in user_stats:
            user_stats[user_id] = {
                'downloads': 0,
                'join_date': datetime.now().strftime('%Y-%m-%d'),
                'last_active': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
        
        stats = user_stats[user_id]
        active_files_count = len([f for f in uploaded_files.values() if f.get('active', False)])
        
        # Category breakdown
        category_counts = {}
        for file_info in uploaded_files.values():
            if file_info.get('active', False):
                category = file_info.get('category', 'other')
                category_counts[category] = category_counts.get(category, 0) + 1
        
        stats_text = f"""
📊 **Your Statistics**

👤 {user.first_name} | ✅ Channel Member

📈 **Activity:**
📅 Member Since: {stats['join_date']}
⬇️ Downloads: {stats['downloads']}
🕐 Last Active: {stats['last_active']}

📁 **Available Content:**
Total Files: {active_files_count}

📂 **Categories:**
        """
        
        for category, count in category_counts.items():
            stats_text += f"{category.title()}: {count} files\n"
        
        keyboard = [
            [InlineKeyboardButton("📁 View Files", callback_data="view_files")],
            [InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
            [InlineKeyboardButton("📂 Categories", callback_data="view_categories")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    async def show_help_inline(self, query):
        """Show help in inline message"""
        help_text = f"""
❓ **Quick Help**

🔐 **Requirements:**
✅ Channel membership required

📋 **Features:**
• 📁 Browse all files
• 🔍 Search by name/type
• 📂 Browse by category
• 📊 View statistics

🎯 **Tips:**
• Use search to find specific files
• Browse categories for organized viewing
• Stay in {CHANNEL_ID} for access
• Files download instantly

Need more help? Use /help command!
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 Browse Files", callback_data="view_files")],
            [InlineKeyboardButton("🔍 Search Files", callback_data="search_prompt")],
            [InlineKeyboardButton("📂 Categories", callback_data="view_categories")],
            [InlineKeyboardButton("📢 Visit Channel", url=CHANNEL_INVITE_LINK)],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup)
    
    async def show_main_menu_inline(self, query):
        """Show main menu in inline message"""
        user = query.from_user
        active_files_count = len([f for f in uploaded_files.values() if f.get('active', False)])
        
        welcome_text = f"""
🤖 Welcome back {user.first_name}! 

✅ Channel member | Ready to explore!

📊 **Quick Info:**
📁 {active_files_count} files available
🔍 Advanced search enabled
📂 Organized by categories

🚀 **Choose an option:**
        """
        
        keyboard = [
            [InlineKeyboardButton("📁 All Files", callback_data="view_files"),
             InlineKeyboardButton("🔍 Search", callback_data="search_prompt")],
            [InlineKeyboardButton("📂 Categories", callback_data="view_categories"),
             InlineKeyboardButton("📊 My Stats", callback_data="user_stats")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)
    
    async def handle_download(self, query, data):
        """Handle file download"""
        short_id = data.replace("dl_", "")
        user_id = query.from_user.id
        
        if short_id not in uploaded_files or not uploaded_files[short_id].get('active', False):
            await query.answer("❌ File not available!")
            return
        
        file_info = uploaded_files[short_id]
        telegram_file_id = file_info['telegram_file_id']
        
        # Update download stats
        file_info['downloads'] += 1
        if user_id in user_stats:
            user_stats[user_id]['downloads'] += 1
        
            caption=f"📁 **{file_info['name']}**\n\n"
            f"📏 Size: {self.format_file_size(file_info['size'])}\n"
            f"🏷️ Category: {file_info.get('category', 'other').title()}\n"
            f"⬇️ Total Downloads: {file_info['downloads']}\n"
            f"📅 Uploaded: {file_info['upload_date']}\n\n"
            f"🙏 Thanks for being a channel member!"
            
        if file_info.get('youtube_link'):
            caption += f"🎥 YouTube: {file_info['youtube_link']}\n"
    
        caption += f"\n🙏 Thanks for being a channel member!"
    
        try:
        # Send the file
            await query.message.reply_document(
            document=telegram_file_id,
            caption=caption
        )
            
            await query.answer("✅ File sent successfully!")
            
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await query.answer("❌ Error sending file!")

    async def handle_youtube_link(self, query, data):
        if query.from_user.id != ADMIN_USER_ID:
            await query.answer("❌ Admin only!")
            return
        
        short_id = data.replace("youtube_", "")
        if short_id in uploaded_files:
        # Store that we're waiting for YouTube link for this file
            user_searches[query.from_user.id] = f"WAITING_FOR_YOUTUBE_{short_id}"
        
            current_link = uploaded_files[short_id].get('youtube_link')
            link_text = f"Current: {current_link}" if current_link else "No link set"
            await query.edit_message_text(
            f"🔗 **Add YouTube Link**\n\n"
            f"📁 **{uploaded_files[short_id]['name']}**\n"
            f"{link_text}\n\n"
            f"📝 **Send the YouTube link as a message:**\n"
            f"Example: https://youtu.be/VIDEO_ID\n\n"
            f"Or send 'remove' to remove existing link."
        )


    
    async def handle_approve(self, query, data):
        """Handle file approval (admin only)"""
        if query.from_user.id != ADMIN_USER_ID:
            await query.answer("❌ Admin only!")
            return
        
        short_id = data.replace("approve_", "")
        
        if short_id in uploaded_files:
            uploaded_files[short_id]['active'] = True
            
            await query.edit_message_text(
                f"✅ **File Approved & Live!**\n\n"
                f"📁 **{uploaded_files[short_id]['name']}**\n"
                f"📏 Size: {self.format_file_size(uploaded_files[short_id]['size'])}\n"
                f"🏷️ Category: {uploaded_files[short_id].get('category', 'other').title()}\n"
                f"📅 Uploaded: {uploaded_files[short_id]['upload_date']}\n\n"
                f"🎉 Channel members can now download this file!"
            )
            await query.answer("✅ File is now available!")
        
    
    async def handle_delete(self, query, data):
        """Handle file deletion (admin only)"""
        if query.from_user.id != ADMIN_USER_ID:
            await query.answer("❌ Admin only!")
            return
        
        short_id = data.replace("delete_", "")
        
        if short_id in uploaded_files:
            file_name = uploaded_files[short_id]['name']
            # Also remove from mapping
            if short_id in file_id_mapping:
                del file_id_mapping[short_id]
            del uploaded_files[short_id]
            
            await query.edit_message_text(
                f"🗑️ **File Deleted Successfully!**\n\n"
                f"📁 **{file_name}** has been permanently removed.\n\n"
                f"Users will no longer be able to access this file."
            )
            await query.answer("🗑️ File deleted!")
    
    async def handle_category_change(self, query, data):
        """Handle category change (admin only)"""
        if query.from_user.id != ADMIN_USER_ID:
            await query.answer("❌ Admin only!")
            return
        
        short_id = data.replace("category_", "")
        
        if short_id in uploaded_files:
            # Show category selection
            keyboard = []
            for category in CATEGORIES.keys():
                keyboard.append([InlineKeyboardButton(
                    f"🏷️ {category.title()}", 
                    callback_data=f"setcat_{short_id}_{category}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data=f"stats_{short_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🏷️ **Change Category**\n\n"
                f"📁 **{uploaded_files[short_id]['name']}**\n"
                f"Current: {uploaded_files[short_id].get('category', 'other').title()}\n\n"
                f"Select new category:",
                reply_markup=reply_markup
            )
    
    async def handle_file_stats(self, query, data):
        """Show file statistics (admin only)"""
        if query.from_user.id != ADMIN_USER_ID:
            await query.answer("❌ Admin only!")
            return
        
        short_id = data.replace("stats_", "")
        
        if short_id in uploaded_files:
            file_info = uploaded_files[short_id]
            status = "🟢 Active" if file_info.get('active', False) else "🔴 Inactive"
            
            stats_text = f"""
📊 **File Statistics**

📁 **{file_info['name']}**

📈 **Stats:**
📏 Size: {self.format_file_size(file_info['size'])}
🏷️ Category: {file_info.get('category', 'other').title()}
⬇️ Downloads: {file_info['downloads']}
📅 Uploaded: {file_info['upload_date']}
🔄 Status: {status}

👥 **Global Stats:**
Total Bot Users: {len(user_stats)}
Total Downloads (All Files): {sum(f['downloads'] for f in uploaded_files.values())}
            """
            
            keyboard = [
                [InlineKeyboardButton("✅ Approve" if not file_info.get('active') else "🔴 Deactivate", 
                                    callback_data=f"approve_{short_id}" if not file_info.get('active') else f"deact_{short_id}")],
                [InlineKeyboardButton("🏷️ Change Category", callback_data=f"category_{short_id}")],
                [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{short_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names)-1:
            size_bytes /= 1024
            i += 1
        return f"{size_bytes:.1f}{size_names[i]}"
    
    def run(self):
        """Run the bot"""
        # Create application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("files", self.files_command))
        self.application.add_handler(CommandHandler("search", self.search_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file_upload))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Start the bot
        print("🤖 Enhanced bot with search and categories starting...")
        self.application.run_polling()

if __name__ == "__main__":
    # Setup instructions
    print("""
🚀 ENHANCED TELEGRAM BOT WITH SEARCH & CATEGORIES:

✨ **New Features:**
• 🔍 Advanced search functionality
• 📂 File categorization (auto-detect)
• 📄 Pagination for large file lists
• 🎯 Interactive search prompts
• 📊 Enhanced statistics

🎯 **Search Capabilities:**
• Search by filename
• Search by file type (pdf, mp4, etc.)
• Search by category
• Interactive search mode

📂 **Categories:**
• 📄 Documents (pdf, doc, txt, etc.)
• 🖼️ Images (jpg, png, gif, etc.)
• 🎥 Videos (mp4, avi, mkv, etc.)
• 🎵 Audio (mp3, wav, flac, etc.)
• 📦 Archives (zip, rar, 7z, etc.)
• 💻 Code (py, js, html, etc.)
• 📁 Other (everything else)

🔧 **Setup Instructions:**
1️⃣ Install: pip install python-telegram-bot
2️⃣ Configure bot token, admin ID, and channel info
3️⃣ Add bot as admin to your channel
4️⃣ Run: python enhanced_bot.py

🎉 **How Users Search:**
• /search [query] - Direct search
• Click "Search" button for interactive mode
• Browse categories for organized viewing
• Use pagination for large lists

🔐 **Admin Features:**
• Auto-categorization on upload
• Category management
• File approval system
• Enhanced statistics

Ready to run! 🚀
    """)
    
    # Initialize and run bot
    bot = TelegramBot()
    bot.run()