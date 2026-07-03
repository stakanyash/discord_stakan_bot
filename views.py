"""Discord UI View классы: кнопки и меню."""

import discord
from discord.ui import Button, View

from database import remove_mute, add_role_user, remove_role_user
from embeds import e_ok, e_err, e_warn, e_info, send_mod_log, LOG_COLORS
from config import MUTE_ROLE_ID
from logging import getLogger

logger = getLogger(__name__)


class UnmuteView(discord.ui.View):
    def __init__(self, user_id: int = 0):
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="Снять мут",
            style=discord.ButtonStyle.danger,
            custom_id=f"unmute:{user_id}",
        )
        btn.callback = self._callback
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                embed=e_err("Нет прав", "У вас нет прав для этого действия."), ephemeral=True
            )
            return

        user_id = int(interaction.data["custom_id"].split(":")[1])
        member = interaction.guild.get_member(user_id)
        if member is None:
            await interaction.response.send_message(
                embed=e_err("Не найден", "Пользователь не найден на сервере."), ephemeral=True
            )
            return

        role = discord.utils.get(interaction.guild.roles, id=MUTE_ROLE_ID)
        if role and role in member.roles:
            await member.remove_roles(role, reason=f"Анмьют через кнопку ({interaction.user})")
            remove_mute(user_id)
            for item in self.children:
                item.disabled = True
                item.label = "Мут снят"
            await interaction.response.edit_message(view=self)
            embed = e_ok("Мут снят", f"{member.mention} размьючен пользователем {interaction.user.mention}.")
            embed.set_footer(text=f"ID: {user_id}")
            await interaction.followup.send(embed=embed)
            logger.info(f"Unmuted {user_id} via button by {interaction.user.id}")
            await send_mod_log("Мут снят", LOG_COLORS["join"], member, moderator=interaction.user, bot=interaction.client)
        else:
            await interaction.response.send_message(
                embed=e_warn("Не замьючен", f"{member.mention} не имеет роли мьюта."), ephemeral=True
            )


class SubscribeView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

        add_btn = discord.ui.Button(
            label="Получить роль",
            style=discord.ButtonStyle.green,
            custom_id=f"subscribe_add_{role_id}"
        )
        add_btn.callback = self._add_callback
        self.add_item(add_btn)

        remove_btn = discord.ui.Button(
            label="Отказаться от роли",
            style=discord.ButtonStyle.red,
            custom_id=f"subscribe_remove_{role_id}"
        )
        remove_btn.callback = self._remove_callback
        self.add_item(remove_btn)

    async def _add_callback(self, interaction: discord.Interaction):
        await self._update_role(interaction, add=True)

    async def _remove_callback(self, interaction: discord.Interaction):
        await self._update_role(interaction, add=False)

    async def _update_role(self, interaction: discord.Interaction, add: bool):
        role = discord.utils.get(interaction.guild.roles, id=self.role_id)
        if role is None:
            await interaction.response.send_message(embed=e_err("Роль не найдена"), ephemeral=True)
            return
        if add:
            if role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                add_role_user(interaction.user.id, self.role_id)
                await interaction.response.send_message(
                    embed=e_ok("Роль выдана", f"Вам выдана роль {role.mention}!"), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=e_info("Уже есть", f"У вас уже есть роль {role.mention}."), ephemeral=True
                )
        else:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                remove_role_user(interaction.user.id)
                await interaction.response.send_message(
                    embed=e_ok("Роль снята", f"Роль {role.mention} удалена."), ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=e_info("Роли нет", f"У вас нет роли {role.mention}."), ephemeral=True
                )


class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=15)
        self.author = author
        self.value: bool | None = None
        self.message: discord.Message | None = None

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Это не ваша кнопка.", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.defer()
        if self.message:
            await self.message.delete()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Это не ваша кнопка.", ephemeral=True)
            return
        self.value = False
        self.stop()
        await interaction.response.defer()
        if self.message:
            await self.message.delete()


class AdminMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Проверить YouTube каналы", style=discord.ButtonStyle.blurple, custom_id="admin_check_yt")
    async def check_yt_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message("Проверяю YouTube каналы...", ephemeral=True)
        from youtube import check_youtube_channels
        await check_youtube_channels(reply_channel=interaction.channel, bot=interaction.client)

    @discord.ui.button(label="Обновить ID последних видео", style=discord.ButtonStyle.green, custom_id="admin_update_ids")
    async def update_ids_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message("Обновляю ID последних видео...", ephemeral=True)
        from youtube import fetch_and_save_latest_video_ids
        await fetch_and_save_latest_video_ids()
        await interaction.followup.send(embed=e_ok("Готово", "ID последних видео обновлены."), ephemeral=True)

    @discord.ui.button(label="Перезагрузить бота", style=discord.ButtonStyle.red, custom_id="admin_restart")
    async def restart_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message(embed=e_warn("Перезагрузка", "Бот перезапускается..."), ephemeral=True)
        import asyncio
        import sys
        import os
        logger.info(f"Bot restarting by {interaction.user}")
        await asyncio.sleep(2)
        os.execv(sys.executable, ['python'] + sys.argv)

    @discord.ui.button(label="Спарсить все видео YouTube", style=discord.ButtonStyle.primary, custom_id="admin_fetch_all_videos")
    async def fetch_all_videos_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(embed=e_err("Нет прав"), ephemeral=True)
            return
        await interaction.response.send_message("Парсю все публичные видео с YouTube каналов...", ephemeral=True)
        from youtube import fetch_all_videos_to_history
        total = await fetch_all_videos_to_history()
        await interaction.followup.send(
            embed=e_ok("Готово", f"Сохранено {total} уникальных видео в историю."),
            ephemeral=True
        )
