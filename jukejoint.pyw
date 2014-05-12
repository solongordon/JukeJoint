import cPickle
import os
import random
import subprocess
import sys
import thread
import wx
from wx.lib.pubsub import Publisher as pub


COVER_FILENAME = "folder.jpg"
DEFAULT_FILTER = "02 popular"
FOLDERS_CHANGED_MSG = "FOLDERS CHANGED"
MUSIC_FILE_EXTENSIONS = ['.mp3', '.flac', '.m4a', '.ogg']


class FolderIterator(object):
    def __init__(self, folders, display_num):
        self._folders = folders
        self._display_num = display_num
        self._filter = ''
        self._current_folder_indices = tuple()
        self._get_new_folders(0)

    def get_current_folders(self):
        return tuple(self._folders[i] for i in self._current_folder_indices)

    def next(self):
        start_idx = self._current_folder_indices[-1] + 1
        self._get_new_folders(start_idx)

    def previous(self):
        start_idx = self._current_folder_indices[0] - 1
        self._get_new_folders(start_idx, True)

    def set_filter(self, keyword):
        if keyword == self._filter:
            # nothing to do
            return
        old_filter = self._filter
        self._filter = keyword
        start_idx = self._current_folder_indices[0]
        try:
            self._get_new_folders(start_idx)
        except IndexError:
            # no results for this filter. fall back to the previous one.
            self._filter = old_filter

    def _get_new_folders(self, start_idx, reversed=False):
        new_folders = []
        idx = start_idx % len(self._folders)
        while len(new_folders) < self._display_num:
            if self._is_displayable(self._folders[idx]):
                if reversed:
                    new_folders.insert(0, idx)
                else:
                    new_folders.append(idx)
            idx += -1 if reversed else 1
            idx %= len(self._folders)
            if idx == start_idx and not new_folders:
                raise IndexError("Found no displayable folders.")
        self._current_folder_indices = tuple(new_folders)
        pub.sendMessage(FOLDERS_CHANGED_MSG, self.get_current_folders())

    def _is_displayable(self, folder):
        return (self._filter in folder and
                self._has_folder_image(folder) and
                self._includes_music(folder))

    def _has_folder_image(self, folder):
        cover_path = os.path.join(folder, COVER_FILENAME)
        return os.path.exists(cover_path)

    def _includes_music(self, folder):
        return any(filename.endswith(extension)
                   for filename in os.listdir(folder)
                   for extension in MUSIC_FILE_EXTENSIONS)


class JukeJointView(wx.Frame):
    def __init__(self, img_size, span):
        size = (img_size*span, img_size*span)
        style = wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR | wx.NO_BORDER
        wx.Frame.__init__(self, None, -1, '', size=size, style=style)
        self.center_on_primary_monitor()
        self.panel = CoversPanel(self, img_size, span)

    def center_on_primary_monitor(self):
        window_width, window_height = self.GetClientSizeTuple()
        for i in range(wx.Display.GetCount()):
            display = wx.Display(i)
            if display.IsPrimary():
                x, y, screen_width, screen_height = display.GetGeometry()
                xpos = (screen_width - window_width) / 2
                ypos = (screen_height - window_height) / 2
                self.SetPosition((xpos, ypos))


class CoversPanel(wx.Panel):
    def __init__(self, parent, img_size, span):
        wx.Panel.__init__(self, parent, -1, style=wx.WANTS_CHARS)
        self.covers = [Cover(self, img_size) for i in range(span * span)]

        self.sizer = wx.GridSizer(span, span, 0, 0)
        self.sizer.AddMany(self.covers)
        self.SetSizer(self.sizer)
        self.Fit()


class Cover(wx.StaticBitmap):
    def __init__(self, parent, img_size):
        self.img_size = img_size
        wx.StaticBitmap.__init__(self, parent, -1, size=(img_size, img_size))


class JukeJoint(object):
    def __init__(self, folder_iterator, player_path, img_size, span):
        self.folder_iterator = folder_iterator
        self.view = JukeJointView(img_size, span)

        self.img_size = img_size
        self.player_path = player_path
        self.search_mode_enabled = False
        self.user_filter = ''

        # Subscribe to folder updates.
        pub.subscribe(self._on_folders_changed, FOLDERS_CHANGED_MSG)
        folder_iterator.set_filter(DEFAULT_FILTER)

        # Set up event listeners.
        self.view.panel.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        for cover in self.view.panel.covers:
            cover.Bind(wx.EVT_LEFT_UP, self._on_left_click)
            cover.Bind(wx.EVT_RIGHT_UP, self._on_right_click)

        self.view.Show()
        self.view.panel.SetFocus()

    def _on_folders_changed(self, message):
        images = (self._get_folder_image(folder) for folder in message.data)
        for cover, image in zip(self.view.panel.covers, images):
            cover.SetBitmap(image)

    def _on_key_down(self, event):
        keycode = event.GetKeyCode()
        if self.search_mode_enabled:
            if ord(' ') <= keycode <= ord('~'):
                self.user_filter += chr(keycode).lower()
            elif keycode == wx.WXK_RETURN:
                self.folder_iterator.set_filter(self.user_filter)
                self.user_filter = ''
                self.search_mode_enabled = False
            elif keycode == wx.WXK_ESCAPE:
                self.user_filter = ''
                self.search_mode_enabled = False
        else:
            if keycode == wx.WXK_ESCAPE:
                self.view.Destroy()
            elif keycode == wx.WXK_F3:
                self.search_mode_enabled = True
            elif keycode in (wx.WXK_SPACE, wx.WXK_DOWN, wx.WXK_RIGHT):
                self.folder_iterator.next()
            elif keycode in (wx.WXK_UP, wx.WXK_LEFT):
                self.folder_iterator.previous()
            elif keycode == ord('A'):
                self.folder_iterator.set_filter('')
            elif keycode == ord('C'):
                self.folder_iterator.set_filter('01 classical')
            elif keycode == ord('P'):
                self.folder_iterator.set_filter('02 popular')
            elif keycode == ord('M'):
                self.folder_iterator.set_filter('03 mixes')
            elif keycode == ord('S'):
                self.folder_iterator.set_filter('04 singles')

    def _on_left_click(self, event):
        cover_idx = self.view.panel.covers.index(event.GetEventObject())
        folder = self.folder_iterator.current_folders()[cover_idx]
        subprocess.Popen([self.player_path, folder])
        self.view.Destroy()

    def _on_right_click(self, event):
        self.folder_iterator.next()

    def _get_folder_image(self, folder):
        image_path = os.path.join(folder, COVER_FILENAME)
        image = wx.Image(image_path)
        image.Rescale(self.img_size, self.img_size, wx.IMAGE_QUALITY_HIGH)
        return wx.BitmapFromImage(image)


def get_music_folders(music_path, pickle_path):
    folders = [path for path, dirs, files in os.walk(music_path)]

    # Pickle folder list for next time.
    out_file = open(pickle_path, 'wb')
    cPickle.dump({music_path: folders}, out_file, protocol=2)
    return folders


if __name__ == '__main__':
    from ConfigParser import SafeConfigParser

    # Parse the config file.
    config = SafeConfigParser()
    script_dir = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(script_dir, 'jukejoint.ini')
    config.read(config_path)
    music_path = config.get(os.name, 'music_path')
    config_path = os.path.expanduser(config.get(os.name, 'config_path'))
    player_path = config.get(os.name, 'player_path')
    img_size = config.getint(os.name, 'img_size')
    span = config.getint(os.name, 'span')

    # Get music folders.
    if not os.path.isdir(music_path):
        sys.exit("No such directory: %s" % music_path)
    try:
        folders = cPickle.load(open(config_path, 'rb'))[music_path]
        thread.start_new_thread(get_music_folders, (music_path, config_path))
    except:
        folders = get_music_folders(music_path)
    random.shuffle(folders)
    folder_iterator = FolderIterator(folders, span * span)

    app = wx.App(0)
    JukeJoint(folder_iterator, player_path, img_size, span)
    app.MainLoop()
