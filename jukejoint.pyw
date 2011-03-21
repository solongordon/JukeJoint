import os
import random
import subprocess
import pickle
import thread

import wx
from wx.lib.pubsub import Publisher as pub

class JukeJointModel(object):
  music_file_extensions = ['.mp3', '.flac', '.m4a', '.ogg']
  
  def __init__(self, display_num, music_path, config_path, player_path):
    self._display_num = display_num
    self._music_path = music_path
    self._config_path = config_path
    self._player_path = player_path

    try:
      self._folders = pickle.load(open(config_path))[music_path]
    except:
      self._folders = self._get_folders()
    random.shuffle(self._folders)

    self._display_folders = []
    self._left_idx = 0
    self._right_idx = 0
    self._filter = ''

    self.search_mode_enabled = False
    self.user_filter = ''

  def get_display_folder(self, num):
    return self._display_folders[num]

  def play(self, folder):
    subprocess.Popen([self._player_path, folder])

  def change_filter(self, keyword):
    if self._filter != keyword:
      self._filter = keyword
      self._refresh_folders()

  def next_folders(self):
    self._display_folders = []
    benchmark_updated = False
    while len(self._display_folders) < self._display_num:
      self._right_idx += 1
      self._right_idx %= len(self._folders)
      folder = self._folders[self._right_idx]
      if self._is_displayable(folder):
        self._display_folders.append(folder)
        if not benchmark_updated:
          self._left_idx = self._right_idx
          benchmark_updated = True
    pub.sendMessage("FOLDERS CHANGED", self._display_folders)

  def previous_folders(self):
    self._display_folders = []
    benchmark_updated = False
    while len(self._display_folders) < self._display_num:
      self._left_idx -= 1
      self._left_idx %= len(self._folders)
      folder = self._folders[self._left_idx]
      if self._is_displayable(folder):
        self._display_folders.insert(0, folder)
        if not benchmark_updated:
          self._right_idx = self._left_idx
          benchmark_updated = True
    pub.sendMessage("FOLDERS CHANGED", self._display_folders)

  def dump_folder_data(self):
    data = {self._music_path: self._get_folders()}
    out_file = open(self._config_path, 'wb')
    pickle.dump(data, out_file)

  def _refresh_folders(self):
    self._display_folders = []
    self._right_idx = self._left_idx - 1
    while len(self._display_folders) < self._display_num:
      self._right_idx += 1
      self._right_idx %= len(self._folders)
      folder = self._folders[self._right_idx]
      if self._is_displayable(folder):
        self._display_folders.append(folder)
    pub.sendMessage("FOLDERS CHANGED", self._display_folders)

  def _is_displayable(self, folder):
    return (self._filter in folder and
            self._has_folder_image(folder) and
            self._includes_music(os.listdir(folder)))

  def _includes_music(self, files):
    for file in files:
      for extension in self.music_file_extensions:
        if file.endswith(extension):
          return True
    return False

  def _has_folder_image(self, folder):
    cover_path = os.path.join(folder, 'folder.jpg')
    return os.path.exists(cover_path)

  def _get_folders(self):
    return [path for path, dirs, files in os.walk(self._music_path)
            if 'folder.jpg' in files and self._includes_music(files)]

class JukeJointView(wx.Frame):
  def __init__(self, parent, img_size, span):
    style = wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR | wx.NO_BORDER
    wx.Frame.__init__(self, parent, -1, 'JukeJoint',
                      size=(img_size*span, img_size*span), style=style)
    self.center_on_primary_monitor()
    self.panel = CoversPanel(self, img_size, span)

  def center_on_primary_monitor(self):
    window_width, window_height = self.GetClientSizeTuple()
    for i in range(wx.Display.GetCount()):
      d = wx.Display(i)
      if d.IsPrimary():
        x, y, screen_width, screen_height = d.GetGeometry()
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

  def set_image(self, image_path):
    image = wx.Image(image_path)
    image.Rescale(self.img_size, self.img_size, wx.IMAGE_QUALITY_HIGH)
    self.SetBitmap(wx.BitmapFromImage(image))

class JukeJointController(object):
  def __init__(self, music_path, config_path, player_path, img_size, span):
    self.model = JukeJointModel(span * span, music_path, config_path,
                                   player_path)
    self.view = JukeJointView(None, img_size, span)
    pub.subscribe(self.folders_changed, "FOLDERS CHANGED")

    self.view.panel.Bind(wx.EVT_KEY_DOWN, self.__on_key_down)
    for cover in self.view.panel.covers:
      cover.Bind(wx.EVT_LEFT_UP, self.__on_left_click)
      cover.Bind(wx.EVT_RIGHT_UP, self.__on_right_click)

    self.model.next_folders()
    self.view.Show()

    thread.start_new_thread(self.model.dump_folder_data, ())
    self.view.panel.SetFocus()

  def folders_changed(self, message):
    folders = message.data
    for cover, folder in zip(self.view.panel.covers, folders):
      image_path = os.path.join(folder, 'folder.jpg')
      cover.set_image(image_path)

  def __on_key_down(self, event):
    keycode = event.GetKeyCode()
    if self.model.search_mode_enabled:
      if ord(' ') <= keycode <= ord('~'):
        self.model.user_filter += chr(keycode).lower()
      elif keycode == wx.WXK_RETURN:
        self.model.change_filter(self.model.user_filter)
        self.model.user_filter = ''
        self.model.search_mode_enabled = False
      elif keycode == wx.WXK_ESCAPE:
        self.model.user_filter = ''
        self.model.search_mode_enabled = False
    else:
      if keycode == wx.WXK_ESCAPE:
        self.view.Destroy()
      elif keycode == wx.WXK_F3:
        self.model.search_mode_enabled = True
      elif keycode in (wx.WXK_SPACE, wx.WXK_DOWN, wx.WXK_RIGHT):
        self.model.next_folders()
      elif keycode in (wx.WXK_UP, wx.WXK_LEFT):
        self.model.previous_folders()
      elif keycode == ord('A'):
        self.model.change_filter('')
      elif keycode == ord('C'):
        self.model.change_filter('01 classical')
      elif keycode == ord('P'):
        self.model.change_filter('02 popular')

  def __on_left_click(self, event):
    cover_num = self.view.panel.covers.index(event.GetEventObject())
    folder = self.model.get_display_folder(cover_num)
    self.model.play(folder)
    self.view.Destroy()

  def __on_right_click(self, event):
    self.model.next_folders()

if __name__ == '__main__':
  from ConfigParser import SafeConfigParser
  config = SafeConfigParser()
  config.read('jukejoint.ini')
  args = [config.get(os.name, 'music_path'),
          os.path.expanduser(config.get(os.name, 'config_path')),
          config.get(os.name, 'player_path'),
          config.getint(os.name, 'img_size'),
          config.getint(os.name, 'span')]

  app = wx.App(0)
  controller = JukeJointController(*args)
  app.MainLoop()
