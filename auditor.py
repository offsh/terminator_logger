# Plugin by Sinan Nalkaya <sardok@gmail.com>
# See LICENSE of Terminator package.

""" auditor.py is a plugin that analyzes the data written to the
terminal and register both user input and console output togeter
into a syslog event logger.
"""

from os.path import expanduser
import os
from gi.repository import Gtk
import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from datetime import datetime

AVAILABLE = ['Auditor']

home_directory = expanduser("~")
datestamp = datetime.today().strftime('%b %d')
timestamp = datetime.today().strftime('%H:%M:%S')

program_name = "Auditor"


class Auditor(plugin.Plugin):

    """ Add custom command to the terminal menu"""
    capabilities = ['terminal_menu']
    log_directory = f"{home_directory}/.session_logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    log_file = f"{log_directory}/{datestamp}.log".replace(" ", "-")
    loggers = None
    dialog_action = Gtk.FileChooserAction.SAVE
    dialog_buttons = (_("_Cancel"), Gtk.ResponseType.CANCEL,
                      _("_Save"), Gtk.ResponseType.OK)

    # -------------------------------------------------------------------------------------------------------------------------

    def __init__(self):
        plugin.MenuItem.__init__(self)

        if not self.loggers:
            self.loggers = {}

    # -------------------------------------------------------------------------------------------------------------------------

    def callback(self, menuitems, menu, terminal):
        """ Add save menu item to the menu"""
        vte_terminal = terminal.get_vte()
        if vte_terminal not in self.loggers:
            item = Gtk.MenuItem.new_with_mnemonic(_('Start logging'))
            item.connect("activate", self.start, terminal)
        else:
            item = Gtk.MenuItem.new_with_mnemonic(_('Stop logging'))
            item.connect("activate", self.stop, terminal)
        menuitems.append(item)

    # -------------------------------------------------------------------------------------------------------------------------

    def start(self, _widget, Terminal):
        """
        Start auditor logger by connecting required callbacks
        """

        vte_terminal = Terminal.get_vte()

        self.loggers[vte_terminal] = {}

        self.loggers[vte_terminal]["last_command"] = ""
        self.loggers[vte_terminal]["commit_handler_id"] = 0
        self.loggers[vte_terminal]["contents_changed_id"] = 0
        self.loggers[vte_terminal]["last_saved_col"] = 0
        self.loggers[vte_terminal]["last_saved_row"] = 0
        self.loggers[vte_terminal]["prompt_offset"] = 0
        self.loggers[vte_terminal]["prompt_string"] = "local"

        # callbacks
        self.commit_handler_id = vte_terminal.connect('commit', self.capture_input)
        self.contents_changed_id = vte_terminal.connect('contents-changed', self.write_console_output)

    # -------------------------------------------------------------------------------------------------------------------------

    def stop(self, _widget, terminal):
        """
        Writes output not logged to the log_file and disconnect callbacks
        """
        vte_terminal = terminal.get_vte()
        last_saved_col = self.loggers[vte_terminal].last_saves_col
        last_saved_row = self.loggers[vte_terminal].last_saves_row
        (current_col, current_row) = vte_terminal.get_cursor_position()
        if last_saved_col != current_col or last_saved_row != current_row:
            missing_output = self.get_content(terminal, last_saved_row, last_saved_col,
                                              current_row, current_col)
        prompt_string = self.loggers[vte_terminal]["prompt_string"]
        self.register_command(self.loggers[vte_terminal]["last_command"], missing_output, prompt_string)
        vte_terminal.disconnect(self.loggers[vte_terminal]["commit_handler_id"])
        vte_terminal.disconnect(self.loggers[vte_terminal]["contents_changed_id"])

        del(self.loggers[vte_terminal])

    # -------------------------------------------------------------------------------------------------------------------------

    def cleanPrompt(self, string):
        clean_prompt = ""
        char_replacement = {
          '@': '@',
          '/': '/',
          '[': '(',
          ']': ')',
          ':': '_'
        }

        for char in string:
            if char.isalnum():
                clean_prompt += char
            elif char in char_replacement.keys():
                clean_prompt += char_replacement[char]
        return clean_prompt

    # -------------------------------------------------------------------------------------------------------------------------


    def capture_input(self, vte_terminal, input_pointer, input_length):
        """ 'commit' signal callback (user input)
        Read user input to terminal (char by char), if it is a return (enter) char,
        record the command introduced into the terminal by the user
        """

        (current_col, current_row) = vte_terminal.get_cursor_position()

        prompt_known = self.loggers[vte_terminal]["prompt_offset"] != 0

        if not prompt_known:
            self.loggers[vte_terminal]["prompt_offset"] = current_col
            prompt = self.get_content(vte_terminal, current_row, 0, current_row, current_col)
            self.loggers[vte_terminal]["prompt_string"] = self.cleanPrompt(prompt)

        input_string = '{: <{}}'.format(input_pointer, input_length)

        print(input_string)

        is_return = input_string == '\r'

        if is_return:
            prompt_offset = self.loggers[vte_terminal]["prompt_offset"]
            command_line = self.get_content(vte_terminal, current_row, 0, current_row, current_col)
            if "[sudo] password for" in command_line:
                return
            self.loggers[vte_terminal]["last_command"] = self.get_content(vte_terminal, current_row, prompt_offset,
                                                                          current_row, current_col)
            self.loggers[vte_terminal]["last_saved_row"] = current_row+1
            self.loggers[vte_terminal]["last_saved_col"] = 0

    # -------------------------------------------------------------------------------------------------------------------------

    def write_console_output(self, vte_terminal):
        """ 'contents-changed' signal callback
        Detect changes on ther terminal output, if an end of command
        is detected, write to the logfile the console output along
        with the user command input
        """

        def get_command_output(content):
            """
            Given a terminal content, replace new lines by spaces and
            remove the prompt so the console output could be logged to
            a single line log.
            """
            console_lines = content.splitlines()
            console_lines = console_lines[:-1]  # removes the prompt
            return ' '.join(console_lines)

        (current_col, current_row) = vte_terminal.get_cursor_position()

        last_saved_col = self.loggers[vte_terminal]["last_saved_col"]
        last_saved_row = self.loggers[vte_terminal]["last_saved_row"]

        console_content = self.get_content(vte_terminal, last_saved_row, last_saved_col,
                                           current_row, current_col)

        is_single_char = "\n" not in console_content
        incomplete_output = console_content.endswith("\n")

        print(console_content)

        if is_single_char:
            return

        elif incomplete_output:
            return

        else:
            command_output = get_command_output(console_content)
            prompt_string = self.loggers[vte_terminal]["prompt_string"]
            self.register_command(self.loggers[vte_terminal]["last_command"], command_output, prompt_string)
            self.loggers[vte_terminal]["last_saved_col"] = current_col
            self.loggers[vte_terminal]["last_saved_row"] = current_row
            self.loggers[vte_terminal]["prompt_offset"] = 0

    # -------------------------------------------------------------------------------------------------------------------------

    def register_command(self, command, output, prompt):
        """
        Creates a log line with both user input and command output and
        register it into the log file
        """
        log_line = f"{datestamp} {timestamp} {prompt} {program_name}: {command} executed with output:  {output}"
        print(log_line)
        self.write_logs(log_line)

    # -------------------------------------------------------------------------------------------------------------------------

    def write_logs(self, log_string):
        """
        Write log_string to the log file
        """
        fd = open(self.log_file, 'a+')
        fd.write(f"{log_string}\n")
        fd.flush()
        fd.close()

    # -------------------------------------------------------------------------------------------------------------------------

    def get_content(self, terminal, row_start, col_start, row_end, col_end):
        """
        Get console content on the area defined by row and col parameters
        """
        content = terminal.get_text_range(row_start, col_start, row_end, col_end, lambda *a: True)
        return content[0]

    # -------------------------------------------------------------------------------------------------------------------------
