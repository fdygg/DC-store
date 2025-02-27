import discord
from discord.ext import commands
import logging
import datetime
from main import is_admin
from database import get_connection, add_balance, subtract_balance

# Konfigurasi logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATABASE = 'store.db'

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_time = datetime.datetime.utcnow()
        self._last_command = {}  # Untuk mencegah duplikasi command

    def db_connect(self):
        return get_connection()

    async def check_duplicate_command(self, ctx, command_name, timeout=3):
        """Mencegah duplikasi command dalam waktu tertentu"""
        current_time = datetime.datetime.utcnow().timestamp()
        user_last_command = self._last_command.get(ctx.author.id, {})
        
        if command_name in user_last_command:
            last_time = user_last_command[command_name]
            if current_time - last_time < timeout:
                await ctx.send("⚠️ Please wait a moment before using this command again.")
                return True

        user_last_command[command_name] = current_time
        self._last_command[ctx.author.id] = user_last_command
        return False

    @commands.command()
    @is_admin()
    async def addProduct(self, ctx, name: str, code: str, price: int, description: str = ""):
        """
        Menambahkan produk baru
        Usage: !addProduct <name> <code> <price> [description]
        """
        logging.info(f'addProduct command invoked by {ctx.author}')
        try:
            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO products (name, code, price, stock, description) 
                VALUES (?, ?, ?, 0, ?)
            """, (name, code, price, description))
            
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Product Added Successfully",
                color=discord.Color.green(),
                timestamp=self.current_time
            )
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Code", value=code, inline=True)
            embed.add_field(name="Price", value=f"{price} WL", inline=True)
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            embed.set_footer(text=f"Added by {ctx.author}")

            await ctx.send(embed=embed)
            logger.info(f'Product {code} added by {ctx.author}')

        except Exception as e:
            logger.error(f'Error in addProduct: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def addStock(self, ctx, product_code: str, *, file_path: str = None):
        """
        Menambahkan stock dari file
        Usage: !addStock <product_code> [file_path]
        """
        if await self.check_duplicate_command(ctx, 'addStock'):
            return

        logging.info(f'addStock command invoked by {ctx.author}')
        try:
            # Handle file path
            if file_path is None:
                if len(ctx.message.attachments) > 0:
                    attachment = ctx.message.attachments[0]
                    await attachment.save(attachment.filename)
                    file_path = attachment.filename
                else:
                    file_path = f'{product_code}.txt'

            # Membaca dan memproses file
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                valid_lines = [line.strip() for line in lines if line.strip()]
                count = len(valid_lines)

                if count == 0:
                    await ctx.send("❌ File is empty or contains no valid content.")
                    return

                conn = self.db_connect()
                if conn is None:
                    await ctx.send("❌ Database connection failed.")
                    return

                cursor = conn.cursor()

                # Create product_stock table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS product_stock (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_code TEXT,
                        content TEXT,
                        used INTEGER DEFAULT 0,
                        used_by TEXT DEFAULT NULL,
                        used_at TIMESTAMP DEFAULT NULL,
                        added_by TEXT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        source_file TEXT,
                        FOREIGN KEY (product_code) REFERENCES products (code)
                    )
                """)

                # Verify product exists
                cursor.execute("SELECT code FROM products WHERE code = ?", (product_code,))
                if not cursor.fetchone():
                    await ctx.send(f"❌ Product with code {product_code} does not exist.")
                    conn.close()
                    return

                # Update stock count
                cursor.execute("""
                    UPDATE products 
                    SET stock = stock + ? 
                    WHERE code = ?
                """, (count, product_code))

                # Insert stock items
                for content in valid_lines:
                    cursor.execute("""
                        INSERT INTO product_stock (
                            product_code, content, added_by, source_file
                        ) VALUES (?, ?, ?, ?)
                    """, (product_code, content, str(ctx.author), file_path))

                conn.commit()
                conn.close()

                # Send confirmation
                embed = discord.Embed(
                    title="✅ Stock Added Successfully",
                    color=discord.Color.green(),
                    timestamp=self.current_time
                )
                embed.add_field(name="Product Code", value=product_code, inline=True)
                embed.add_field(name="Items Added", value=str(count), inline=True)
                embed.add_field(name="Source File", value=file_path, inline=True)
                embed.set_footer(text=f"Added by {ctx.author}")

                await ctx.send(embed=embed)
                logger.info(f'Added {count} stock items to {product_code} by {ctx.author}')

        except FileNotFoundError:
            await ctx.send(f"❌ File not found: {file_path}")
        except Exception as e:
            logger.error(f'Error in addStock: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def deleteProduct(self, ctx, code: str):
        """
        Menghapus produk dan stoknya
        Usage: !deleteProduct <code>
        """
        if await self.check_duplicate_command(ctx, 'deleteProduct'):
            return

        logging.info(f'deleteProduct command invoked by {ctx.author}')
        try:
            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()
            
            # Get product info before deletion
            cursor.execute("SELECT name FROM products WHERE code = ?", (code,))
            product = cursor.fetchone()
            
            if not product:
                await ctx.send(f"❌ Product with code {code} does not exist.")
                conn.close()
                return

            # Delete product and its stock
            cursor.execute("DELETE FROM products WHERE code = ?", (code,))
            cursor.execute("DELETE FROM product_stock WHERE product_code = ?", (code,))
            
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Product Deleted Successfully",
                description=f"Product `{code}` and its stock have been deleted.",
                color=discord.Color.red(),
                timestamp=self.current_time
            )
            embed.set_footer(text=f"Deleted by {ctx.author}")

            await ctx.send(embed=embed)
            logger.info(f'Product {code} deleted by {ctx.author}')

        except Exception as e:
            logger.error(f'Error in deleteProduct: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def addBal(self, ctx, growid: str, wl: int = 0, dl: int = 0, bgl: int = 0):
        """
        Menambah balance user
        Usage: !addBal <growid> <wl> [dl] [bgl]
        """
        if await self.check_duplicate_command(ctx, 'addBal'):
            return

        logging.info(f'addBal command invoked by {ctx.author}')
        try:
            # Validasi input
            if wl < 0 or dl < 0 or bgl < 0:
                await ctx.send("❌ Amount must be positive!")
                return

            if wl == 0 and dl == 0 and bgl == 0:
                await ctx.send("❌ Please specify at least one currency amount!")
                return

            # Add balance
            add_balance(growid, wl, dl, bgl)

            # Get updated balance
            conn = self.db_connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users 
                WHERE growid = ?
            """, (growid,))
            balance = cursor.fetchone()
            conn.close()

            if balance:
                balance_wl, balance_dl, balance_bgl = balance
                embed = discord.Embed(
                    title="💰 Balance Added Successfully",
                    color=discord.Color.green(),
                    timestamp=self.current_time
                )
                embed.add_field(name="GrowID", value=growid, inline=True)
                
                added_amounts = []
                if wl > 0: added_amounts.append(f"{wl:,} WL")
                if dl > 0: added_amounts.append(f"{dl:,} DL")
                if bgl > 0: added_amounts.append(f"{bgl:,} BGL")
                embed.add_field(
                    name="Amount Added", 
                    value=", ".join(added_amounts), 
                    inline=True
                )
                
                embed.add_field(
                    name="Current Balance",
                    value=f"```\n{balance_wl:,} WL\n{balance_dl:,} DL\n{balance_bgl:,} BGL```",
                    inline=False
                )
                embed.set_footer(text=f"Added by {ctx.author}")

                await ctx.send(embed=embed)
                logger.info(f'Added {wl} WL, {dl} DL, {bgl} BGL to {growid} by {ctx.author}')
            else:
                await ctx.send("❌ Failed to retrieve updated balance!")

        except Exception as e:
            logger.error(f'Error in addBal: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def reduceBal(self, ctx, growid: str, wl: int = 0, dl: int = 0, bgl: int = 0):
        """
        Mengurangi balance user
        Usage: !reduceBal <growid> <wl> [dl] [bgl]
        """
        if await self.check_duplicate_command(ctx, 'reduceBal'):
            return

        logging.info(f'reduceBal command invoked by {ctx.author}')
        try:
            # Validasi input
            if wl < 0 or dl < 0 or bgl < 0:
                await ctx.send("❌ Amount must be positive!")
                return

            if wl == 0 and dl == 0 and bgl == 0:
                await ctx.send("❌ Please specify at least one currency amount!")
                return

            # Reduce balance
            subtract_balance(growid, wl, dl, bgl)

            # Get updated balance
            conn = self.db_connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl 
                FROM users 
                WHERE growid = ?
            """, (growid,))
            balance = cursor.fetchone()
            conn.close()

            if balance:
                balance_wl, balance_dl, balance_bgl = balance
                embed = discord.Embed(
                    title="💰 Balance Reduced Successfully",
                    color=discord.Color.red(),
                    timestamp=self.current_time
                )
                embed.add_field(name="GrowID", value=growid, inline=True)
                
                reduced_amounts = []
                if wl > 0: reduced_amounts.append(f"{wl:,} WL")
                if dl > 0: reduced_amounts.append(f"{dl:,} DL")
                if bgl > 0: reduced_amounts.append(f"{bgl:,} BGL")
                embed.add_field(
                    name="Amount Reduced", 
                    value=", ".join(reduced_amounts), 
                    inline=True
                )
                
                embed.add_field(
                    name="Current Balance",
                    value=f"```\n{balance_wl:,} WL\n{balance_dl:,} DL\n{balance_bgl:,} BGL```",
                    inline=False
                )
                embed.set_footer(text=f"Reduced by {ctx.author}")

                await ctx.send(embed=embed)
                logger.info(f'Reduced {wl} WL, {dl} DL, {bgl} BGL from {growid} by {ctx.author}')
            else:
                await ctx.send("❌ Failed to retrieve updated balance!")

        except Exception as e:
            logger.error(f'Error in reduceBal: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def changePrice(self, ctx, code: str, new_price: int):
        """
        Mengubah harga produk
        Usage: !changePrice <code> <new_price>
        """
        if await self.check_duplicate_command(ctx, 'changePrice'):
            return

        logging.info(f'changePrice command invoked by {ctx.author}')
        try:
            if new_price < 0:
                await ctx.send("❌ Price must be positive!")
                return

            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()
            
            # Check if product exists and get old price
            cursor.execute("SELECT name, price FROM products WHERE code = ?", (code,))
            product = cursor.fetchone()
            
            if not product:
                await ctx.send(f"❌ Product with code {code} does not exist.")
                conn.close()
                return

            name, old_price = product

            # Update price
            cursor.execute("""
                UPDATE products 
                SET price = ? 
                WHERE code = ?
            """, (new_price, code))
            
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Price Changed Successfully",
                color=discord.Color.blue(),
                timestamp=self.current_time
            )
            embed.add_field(name="Product", value=name, inline=True)
            embed.add_field(name="Code", value=code, inline=True)
            embed.add_field(name="Old Price", value=f"{old_price:,} WL", inline=True)
            embed.add_field(name="New Price", value=f"{new_price:,} WL", inline=True)
            embed.set_footer(text=f"Changed by {ctx.author}")

            await ctx.send(embed=embed)
            logger.info(f'Price of product {code} changed from {old_price} to {new_price} by {ctx.author}')

        except Exception as e:
            logger.error(f'Error in changePrice: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def setDescription(self, ctx, code: str, *, description: str):
        """
        Mengubah deskripsi produk
        Usage: !setDescription <code> <description>
        """
        if await self.check_duplicate_command(ctx, 'setDescription'):
            return

        logging.info(f'setDescription command invoked by {ctx.author}')
        try:
            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()
            
            # Check if product exists
            cursor.execute("SELECT name FROM products WHERE code = ?", (code,))
            product = cursor.fetchone()
            
            if not product:
                await ctx.send(f"❌ Product with code {code} does not exist.")
                conn.close()
                return

            # Update description
            cursor.execute("""
                UPDATE products 
                SET description = ? 
                WHERE code = ?
            """, (description, code))
            
            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ Description Updated Successfully",
                color=discord.Color.blue(),
                timestamp=self.current_time
            )
            embed.add_field(name="Product", value=product[0], inline=True)
            embed.add_field(name="Code", value=code, inline=True)
            embed.add_field(name="New Description", value=description, inline=False)
            embed.set_footer(text=f"Updated by {ctx.author}")

            await ctx.send(embed=embed)
            logger.info(f'Description of product {code} updated by {ctx.author}')

        except Exception as e:
            logger.error(f'Error in setDescription: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def setWorld(self, ctx, world: str, owner: str, bot_name: str):
        """
        Mengatur informasi world
        Usage: !setWorld <world> <owner> <bot_name>
        """
        if await self.check_duplicate_command(ctx, 'setWorld'):
            return

        logging.info(f'setWorld command invoked by {ctx.author}')
        try:
            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()
            
            # Check current world info
            cursor.execute("SELECT world, owner, bot FROM world_info WHERE id = 1")
            existing = cursor.fetchone()

            # Update or insert world info
            if existing:
                if existing == (world, owner, bot_name):
                    await ctx.send(f"⚠️ World info is already set to these values.")
                    conn.close()
                    return
                    
                cursor.execute("""
                    UPDATE world_info 
                    SET world = ?, owner = ?, bot = ? 
                    WHERE id = 1
                """, (world, owner, bot_name))
            else:
                cursor.execute("""
                    INSERT INTO world_info (id, world, owner, bot) 
                    VALUES (1, ?, ?, ?)
                """, (world, owner, bot_name))

            conn.commit()
            conn.close()

            embed = discord.Embed(
                title="✅ World Info Updated Successfully",
                color=discord.Color.blue(),
                timestamp=self.current_time
            )
            embed.add_field(name="World", value=world, inline=True)
            embed.add_field(name="Owner", value=owner, inline=True)
            embed.add_field(name="Bot", value=bot_name, inline=True)
            if existing:
                embed.add_field(
                    name="Previous Values",
                    value=f"World: {existing[0]}\nOwner: {existing[1]}\nBot: {existing[2]}",
                    inline=False
                )
            embed.set_footer(text=f"Updated by {ctx.author}")

            await ctx.send(embed=embed)
            logger.info(f'World info updated to {world}/{owner}/{bot_name} by {ctx.author}')

        except Exception as e:
            logger.error(f'Error in setWorld: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def send(self, ctx, user: discord.User, code: str, count: int):
        """
        Mengirim produk ke user
        Usage: !send <@user> <product_code> <count>
        """
        if await self.check_duplicate_command(ctx, 'send'):
            return

        logging.info(f'send command invoked by {ctx.author}')
        try:
            if count <= 0:
                await ctx.send("❌ Count must be positive!")
                return

            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return

            cursor = conn.cursor()

            # Get available stock items
            cursor.execute("""
                SELECT id, content 
                FROM product_stock 
                WHERE product_code = ? AND used = 0 
                LIMIT ?
            """, (code, count))
            
            items = cursor.fetchall()
            if not items:
                await ctx.send("❌ No stock available.")
                conn.close()
                return
            
            if len(items) < count:
                await ctx.send(f"❌ Not enough stock available. Only {len(items)} items left.")
                conn.close()
                return

            # Update stock status
            current_time = self.current_time.strftime('%Y-%m-%d %H:%M:%S')
            for item_id, _ in items:
                cursor.execute("""
                    UPDATE product_stock 
                    SET used = 1, used_by = ?, used_at = ? 
                    WHERE id = ?
                """, (str(user), current_time, item_id))

            # Update product stock count
            cursor.execute("""
                UPDATE products 
                SET stock = stock - ? 
                WHERE code = ?
            """, (len(items), code))

            conn.commit()

            # Get product info for embed
            cursor.execute("""
                SELECT name, price 
                FROM products 
                WHERE code = ?
            """, (code,))
            product = cursor.fetchone()
            
            conn.close()

            # Send items to user
            content_message = f"You received {len(items)} items of {code}:\n\n"
            for i, (_, content) in enumerate(items, 1):
                content_message += f"{i}. {content}\n"

            try:
                if len(content_message) > 1900:
                    parts = [content_message[i:i+1900] for i in range(0, len(content_message), 1900)]
                    for part in parts:
                        await user.send(part)
                else:
                    await user.send(content_message)

                # Send confirmation embed
                embed = discord.Embed(
                    title="✅ Items Sent Successfully",
                    color=discord.Color.green(),
                    timestamp=self.current_time
                )
                embed.add_field(name="Recipient", value=user.mention, inline=True)
                embed.add_field(name="Product", value=product[0] if product else code, inline=True)
                embed.add_field(name="Amount", value=str(len(items)), inline=True)
                embed.set_footer(text=f"Sent by {ctx.author}")

                await ctx.send(embed=embed)
                logger.info(f'Sent {len(items)} items of {code} to {user} by {ctx.author}')

            except discord.Forbidden:
                await ctx.send("❌ Could not send DM to user. Please ask them to enable DMs.")
                logger.warning(f'Failed to send DM to {user} for product {code}')

        except Exception as e:
            logger.error(f'Error in send: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def checkStock(self, ctx, product_code: str):
        """
        Memeriksa status stok produk
        Usage: !checkStock <product_code>
        """
        if await self.check_duplicate_command(ctx, 'checkStock'):
            return

        logging.info(f'checkStock command invoked by {ctx.author}')
        try:
            conn = self.db_connect()
            if conn is None:
                await ctx.send("❌ Database connection failed.")
                return
                
            cursor = conn.cursor()
            
            # Get product info
            cursor.execute("""
                SELECT name, price, description 
                FROM products 
                WHERE code = ?
            """, (product_code,))
            
            product_info = cursor.fetchone()
            if not product_info:
                await ctx.send(f"❌ Product with code `{product_code}` does not exist.")
                conn.close()
                return

            name, price, description = product_info
            
            # Get stock stats
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN used = 0 THEN 1 END) as available,
                    COUNT(CASE WHEN used = 1 THEN 1 END) as used,
                    COUNT(*) as total,
                    MAX(added_at) as last_added,
                    MAX(used_at) as last_used
                FROM product_stock 
                WHERE product_code = ?
            """, (product_code,))
            
            stats = cursor.fetchone()
            available, used, total, last_added, last_used = stats
            
            embed = discord.Embed(
                title=f"📊 Stock Status: {name}",
                color=discord.Color.blue(),
                timestamp=self.current_time
            )
            
            embed.add_field(name="Product Code", value=f"`{product_code}`", inline=True)
            embed.add_field(name="Price", value=f"`{price:,} WL`", inline=True)
            embed.add_field(name="Available", value=f"`{available:,}`", inline=True)
            embed.add_field(name="Used", value=f"`{used:,}`", inline=True)
            embed.add_field(name="Total", value=f"`{total:,}`", inline=True)
            
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            if last_added:
                embed.add_field(name="Last Added", value=last_added, inline=False)
            if last_used:
                embed.add_field(name="Last Used", value=last_used, inline=False)
            
            embed.set_footer(text=f"Requested by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            conn.close()
            logger.info(f'Stock checked for {product_code} by {ctx.author}')
            
        except Exception as e:
            logger.error(f'Error in checkStock: {e}')
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    @is_admin()
    async def clearChat(self, ctx, amount: int = None):
        """
        Membersihkan pesan dalam channel
        Usage: !clearChat [amount]
        """
        if await self.check_duplicate_command(ctx, 'clearChat'):
            return

        try:
            # Delete command message first
            await ctx.message.delete()

            if amount is None:
                # Clear all messages
                messages = []
                async for message in ctx.channel.history(limit=None):
                    messages.append(message)
                
                if not messages:
                    error_msg = await ctx.send("❌ No messages to delete!")
                    await error_msg.delete(delay=3)
                    return

                # Delete in chunks of 100
                while messages:
                    chunk = messages[:100]
                    messages = messages[100:]
                    await ctx.channel.delete_messages(chunk)
                
                confirm_msg = await ctx.send("✅ All messages have been cleared!")
                await confirm_msg.delete(delay=3)
            else:
                if amount < 1:
                    error_msg = await ctx.send("❌ Please specify a positive number!")
                    await error_msg.delete(delay=3)
                    return
                
                deleted = await ctx.channel.purge(limit=amount)
                confirm_msg = await ctx.send(f"✅ Deleted {len(deleted)} messages!")
                await confirm_msg.delete(delay=3)

            logger.info(
                f'Chat cleared in #{ctx.channel.name} by {ctx.author} '
                f'at {self.current_time.strftime("%Y-%m-%d %H:%M:%S UTC")}'
            )

        except discord.Forbidden:
            error_msg = await ctx.send("❌ I don't have permission to delete messages!")
            await error_msg.delete(delay=3)
        except discord.HTTPException as e:
            error_msg = await ctx.send(f"❌ An error occurred: {str(e)}")
            await error_msg.delete(delay=3)
            logger.error(f'Error in clearChat: {e}')
        except Exception as e:
            error_msg = await ctx.send("❌ An unexpected error occurred!")
            await error_msg.delete(delay=3)
            logger.error(f'Unexpected error in clearChat: {e}')

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))