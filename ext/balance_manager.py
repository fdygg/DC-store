import discord
from discord.ext import commands
import logging
from database import get_connection
from datetime import datetime

logger = logging.getLogger(__name__)

class BalanceManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def add_balance(self, ctx, growid: str, amount: int, currency: str):
        """Add balance to user"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Verify currency
            currency = currency.upper()
            if currency not in ['WL', 'DL', 'BGL']:
                return "❌ Invalid currency! Use WL, DL, or BGL"
                
            # Get current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl
                FROM users
                WHERE growid = ?
            """, (growid,))
            
            balance = cursor.fetchone()
            if not balance:
                cursor.execute("""
                    INSERT INTO users (growid, balance_wl, balance_dl, balance_bgl)
                    VALUES (?, 0, 0, 0)
                """, (growid,))
                balance = (0, 0, 0)
            
            old_wl, old_dl, old_bgl = balance
            
            # Update balance based on currency
            if currency == 'WL':
                new_wl = old_wl + amount
                new_dl = old_dl
                new_bgl = old_bgl
            elif currency == 'DL':
                new_wl = old_wl
                new_dl = old_dl + amount
                new_bgl = old_bgl
            else:  # BGL
                new_wl = old_wl
                new_dl = old_dl
                new_bgl = old_bgl + amount
                
            # Update balance
            cursor.execute("""
                UPDATE users
                SET balance_wl = ?, balance_dl = ?, balance_bgl = ?
                WHERE growid = ?
            """, (new_wl, new_dl, new_bgl, growid))
            
            # Log transaction
            cursor.execute("""
                INSERT INTO transaction_log (
                    growid, amount, type, details,
                    old_balance, new_balance, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                growid,
                amount,
                'ADMIN_ADD',
                f"Added {amount} {currency} by {ctx.author}",
                f"WL: {old_wl}, DL: {old_dl}, BGL: {old_bgl}",
                f"WL: {new_wl}, DL: {new_dl}, BGL: {new_bgl}"
            ))
            
            conn.commit()
            
            # Return success embed
            embed = discord.Embed(
                title="✅ Balance Added Successfully",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=growid, inline=True)
            embed.add_field(name="Amount Added", value=f"{amount} {currency}", inline=True)
            embed.add_field(name="Added By", value=ctx.author.name, inline=True)
            embed.add_field(name="Old Balance", value=f"WL: {old_wl}\nDL: {old_dl}\nBGL: {old_bgl}", inline=False)
            embed.add_field(name="New Balance", value=f"WL: {new_wl}\nDL: {new_dl}\nBGL: {new_bgl}", inline=False)
            
            return embed
            
        except Exception as e:
            logger.error(f"Error adding balance: {e}")
            if conn:
                conn.rollback()
            return f"❌ An error occurred: {str(e)}"
            
        finally:
            if conn:
                conn.close()

    async def remove_balance(self, ctx, growid: str, amount: int, currency: str):
        """Remove balance from user"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Verify currency
            currency = currency.upper()
            if currency not in ['WL', 'DL', 'BGL']:
                return "❌ Invalid currency! Use WL, DL, or BGL"
                
            # Get current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl
                FROM users
                WHERE growid = ?
            """, (growid,))
            
            balance = cursor.fetchone()
            if not balance:
                return "❌ User not found!"
                
            old_wl, old_dl, old_bgl = balance
            
            # Calculate new balance
            if currency == 'WL':
                if old_wl < amount:
                    return "❌ Insufficient WL balance!"
                new_wl = old_wl - amount
                new_dl = old_dl
                new_bgl = old_bgl
            elif currency == 'DL':
                if old_dl < amount:
                    return "❌ Insufficient DL balance!"
                new_wl = old_wl
                new_dl = old_dl - amount
                new_bgl = old_bgl
            else:  # BGL
                if old_bgl < amount:
                    return "❌ Insufficient BGL balance!"
                new_wl = old_wl
                new_dl = old_dl
                new_bgl = old_bgl - amount
                
            # Update balance
            cursor.execute("""
                UPDATE users
                SET balance_wl = ?, balance_dl = ?, balance_bgl = ?
                WHERE growid = ?
            """, (new_wl, new_dl, new_bgl, growid))
            
            # Log transaction
            cursor.execute("""
                INSERT INTO transaction_log (
                    growid, amount, type, details,
                    old_balance, new_balance, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                growid,
                amount,
                'ADMIN_REMOVE',
                f"Removed {amount} {currency} by {ctx.author}",
                f"WL: {old_wl}, DL: {old_dl}, BGL: {old_bgl}",
                f"WL: {new_wl}, DL: {new_dl}, BGL: {new_bgl}"
            ))
            
            conn.commit()
            
            # Return success embed
            embed = discord.Embed(
                title="✅ Balance Removed Successfully",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=growid, inline=True)
            embed.add_field(name="Amount Removed", value=f"{amount} {currency}", inline=True)
            embed.add_field(name="Removed By", value=ctx.author.name, inline=True)
            embed.add_field(name="Old Balance", value=f"WL: {old_wl}\nDL: {old_dl}\nBGL: {old_bgl}", inline=False)
            embed.add_field(name="New Balance", value=f"WL: {new_wl}\nDL: {new_dl}\nBGL: {new_bgl}", inline=False)
            
            return embed
            
        except Exception as e:
            logger.error(f"Error removing balance: {e}")
            if conn:
                conn.rollback()
            return f"❌ An error occurred: {str(e)}"
            
        finally:
            if conn:
                conn.close()

    async def set_balance(self, ctx, growid: str, wl: int = 0, dl: int = 0, bgl: int = 0):
        """Set user balance directly"""
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Get current balance
            cursor.execute("""
                SELECT balance_wl, balance_dl, balance_bgl
                FROM users
                WHERE growid = ?
            """, (growid,))
            
            old_balance = cursor.fetchone()
            if not old_balance:
                old_wl, old_dl, old_bgl = 0, 0, 0
                cursor.execute("""
                    INSERT INTO users (growid, balance_wl, balance_dl, balance_bgl)
                    VALUES (?, ?, ?, ?)
                """, (growid, wl, dl, bgl))
            else:
                old_wl, old_dl, old_bgl = old_balance
                cursor.execute("""
                    UPDATE users
                    SET balance_wl = ?, balance_dl = ?, balance_bgl = ?
                    WHERE growid = ?
                """, (wl, dl, bgl, growid))
            
            # Log transaction
            cursor.execute("""
                INSERT INTO transaction_log (
                    growid, amount, type, details,
                    old_balance, new_balance, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                growid,
                0,
                'ADMIN_SET',
                f"Balance set by {ctx.author}",
                f"WL: {old_wl}, DL: {old_dl}, BGL: {old_bgl}",
                f"WL: {wl}, DL: {dl}, BGL: {bgl}"
            ))
            
            conn.commit()
            
            # Return success embed
            embed = discord.Embed(
                title="✅ Balance Set Successfully",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="GrowID", value=growid, inline=True)
            embed.add_field(name="Set By", value=ctx.author.name, inline=True)
            embed.add_field(name="Old Balance", value=f"WL: {old_wl}\nDL: {old_dl}\nBGL: {old_bgl}", inline=False)
            embed.add_field(name="New Balance", value=f"WL: {wl}\nDL: {dl}\nBGL: {bgl}", inline=False)
            
            return embed
            
        except Exception as e:
            logger.error(f"Error setting balance: {e}")
            if conn:
                conn.rollback()
            return f"❌ An error occurred: {str(e)}"
            
        finally:
            if conn:
                conn.close()

async def setup(bot):
    await bot.add_cog(BalanceManager(bot))