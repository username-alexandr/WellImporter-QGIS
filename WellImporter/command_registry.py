# -*- coding: utf-8 -*-

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginCommand:
    """Одна запускаемая команда Well Importer."""
    command_id: str
    title: str
    keywords: str
    action: object

    @property
    def search_text(self):
        return f"{self.title} {self.keywords}".lower().replace("ё", "е")

    def trigger(self):
        self.action.trigger()


class CommandRegistry:
    """Стабильный реестр команд для палитры и будущих горячих клавиш."""

    def __init__(self):
        self._commands = []
        self._ids = set()

    def register_action(self, command_id, action, keywords=""):
        command_id = str(command_id).strip()
        if not command_id or command_id in self._ids:
            raise ValueError(f"Повторяющийся ID команды: {command_id}")
        title = str(action.text()).replace("&", "").strip()
        command = PluginCommand(command_id, title, str(keywords), action)
        self._ids.add(command_id)
        self._commands.append(command)
        return command

    def commands(self):
        return list(self._commands)

    def by_id(self, command_id):
        for command in self._commands:
            if command.command_id == command_id:
                return command
        return None
