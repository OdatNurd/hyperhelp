import sublime
import sublime_plugin

import re
import webbrowser

from .output_view import find_view, output_to_view


###----------------------------------------------------------------------------


def log(message, *args, status=False, dialog=False):
    message = message % args
    print("HyperHelp:", message)
    if status:
        sublime.status_message(message)
    if dialog:
        sublime.message_dialog(message)


###----------------------------------------------------------------------------


class HelpCommand(sublime_plugin.ApplicationCommand):
    """
    Open  the help system or focus the current help view. The command can
    optionally open a panel with help topics, take the topic to jump to
    directly, or collect the topic from the cursor location inside of a help
    document.

    """
    def __init__(self):
        self._prefix = "Packages/%s/doc" % __name__.split(".")[0]
        self._url_re = re.compile("^(https?|file)://")

    @classmethod
    def focus(cls, view, pos):
        pos = sublime.Region(pos.end(), pos.begin())

        view.show_at_center(pos)
        view.sel().clear()
        view.sel().add(pos)

        # Hack to make the view update properly. See:
        #    https://github.com/SublimeTextIssues/Core/issues/485
        view.add_regions("_hh_rk", [], "", "", sublime.HIDDEN)
        view.erase_regions("_hh_rk")

    def load_json(self):
        if hasattr(self, "_topics"):
            return

        def help_dict(topic_data, help_file):
            if isinstance(topic_data, str):
                return (topic_data, {
                    "caption": topic_data,
                    "file": help_file
                })

            topic = topic_data.pop("topic", None)
            topic_data["file"] = help_file
            if "caption" not in topic_data:
                topic_data["caption"] = help_file

            return (topic, topic_data)

        toc_file = "%s/index.json" % self._prefix
        self._topics = dict()
        self._toc = list()

        try:
            json = sublime.load_resource(toc_file)
            raw_dict = sublime.decode_value(json)

        except:
            return log("Unable to load help index from '%s'", toc_file)

        topics = dict()
        toc = raw_dict.pop("__toc", None)

        for help_file in raw_dict:
            topic_list = raw_dict[help_file]

            for topic_entry in topic_list:
                topic, topic_entry = help_dict(topic_entry, help_file)
                if topic is None:
                    return log("Entry missing topic: %s", str(topic_entry))

                topics[topic] = topic_entry

        if toc is None:
            toc = sorted(topics.keys())

        self._topics = topics
        self._toc = toc

    def help_content(self, help_file):
        filename = "%s/%s" % (self._prefix, help_file)
        try:
            return sublime.load_resource(filename)
        except:
            pass

        return None

    def topic_file(self, topic):
        self.load_json()
        return self._topics.get(topic, {}).get("file", None)

    def show_file(self, help_file):
        window = sublime.active_window()
        view = find_view(window, "HyperHelp")

        if view is not None:
            window.focus_view(view)
            if help_file == view.settings().get("_hh_file", None):
                return view

        help_text = self.help_content(help_file)
        if help_text is not None:
            view = output_to_view(window,
                                  "HyperHelp",
                                  help_text,
                                  syntax="Packages/HyperHelp/Help.sublime-syntax")
            view.settings().set("_hh_file", help_file)
            return view

        return None

    def show_topic(self, topic):
        help_file = self.topic_file(topic)
        if help_file is None:
            return log("Unknown help topic '%s'", topic, status=True)

        if self._url_re.match(help_file):
            return webbrowser.open_new_tab(help_file)

        help_view = self.show_file(help_file)
        if help_view is None:
            return log("Unable to load help file '%s'", help_file, status=True)

        for pos in help_view.find_by_selector('meta.link-target'):
            target = help_view.substr(pos)
            if target == topic:
                return self.focus(help_view, pos)

        log("Unable to find topic '%s' in help file '%s'", topic, help_file,
            status=True)

    def show_toc(self):
        self.load_json()

        options = []
        for topic in self._toc:
            data = self._topics.get(topic, None)
            options.append([data.get("caption", topic), topic])

        def pick(index):
            if index >= 0:
                self.show_topic(options[index][-1])

        sublime.active_window().show_quick_panel(options, pick)

    def extract_topic(self):
        view = sublime.active_window().active_view()
        point = view.sel()[0].begin()

        if view.match_selector(point, "text.help meta.link"):
            return view.substr(view.extract_scope(point))

        return None

    def run(self, toc=False, topic=None):
        if toc:
            return self.show_toc()

        if topic is None:
            topic = self.extract_topic() or "index.txt"

        self.show_topic(topic)


###----------------------------------------------------------------------------


class HelpNavLinkCommand(sublime_plugin.WindowCommand):
    """
    Advance the cursor to the next or previous link based on the current
    cursor location.
    """
    def run(self, prev=False):
        view = self.window.active_view()
        point = view.sel()[0].begin()

        targets = view.find_by_selector("meta.link")
        fallback = targets[-1] if prev else targets[0]

        def pick(pos):
            other = pos.begin()
            return (point < other) if not prev else (point > other)

        for pos in reversed(targets) if prev else targets:
            if pick(pos):
                return HelpCommand.focus(view, pos)

        HelpCommand.focus(view, fallback)


###----------------------------------------------------------------------------


class HelpListener(sublime_plugin.EventListener):
    """
    Listen for double clicks in help files and, if they occur over links,
    follow the link instead of selecting the text.
    """
    def on_text_command(self, view, command, args):
        if command == "drag_select" and args.get("by", None) == "words":
            event = args["event"]
            point = view.window_to_text((event["x"], event["y"]))

            if view.match_selector(point, "text.help meta.link"):
                sublime.run_command("help")
                return ("noop")

        return None


###----------------------------------------------------------------------------
