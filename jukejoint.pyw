import cPickle
import os
import random
import subprocess
import thread
import wx
from wx.lib.pubsub import Publisher as pub

class JukeJointModel(object):
  music_file_extensions = ['.mp3', '.flac', '.m4a', '.ogg']
  cover_filename = 'folder.jpg'
  
  def __init__(self, display_num, music_path, config_path, player_path):
    self._display_num = display_num
    self._music_path = music_path
    self._config_path = config_path
    self._player_path = player_path
    
    self._display_folders = []
    self._filter = '02 popular'
    self._benchmark = 0
    self.search_mode_enabled = False
    self.user_filter = ''

    try:
      self._folders = cPickle.load(open(config_path, 'rb'))[music_path]
      thread.start_new_thread(self._get_music_folders, ())
    except:
      self._folders = self._get_music_folders()
    random.shuffle(self._folders)

  def play(self, display_idx):
    folder_idx = self._display_folders[display_idx]
    folder = self._get_folder(folder_idx)
    subprocess.Popen([self._player_path, folder])

  def change_filter(self, keyword):
    if self._filter != keyword:
      self._filter = keyword
      self.refresh_folders()

  def refresh_folders(self):
    start_idx = self._benchmark
    self._display_folders = self._get_new_folders(self._display_num,
                                                  start_idx)
    self._send_new_image_paths()

  def next_folders(self):
    start_idx = self._display_folders[-1] + 1
    self._display_folders = self._get_new_folders(self._display_num, 
                                                  start_idx)
    self._benchmark = self._display_folders[0]
    self._send_new_image_paths()

  def previous_folders(self):
    start_idx = self._display_folders[0] - 1
    self._display_folders = self._get_new_folders(self._display_num,
                                                  start_idx,
                                                  step=-1)
    self._benchmark = self._display_folders[0]
    self._send_new_image_paths()

  def _get_music_folders(self):
    folders = [path for path, dirs, files in os.walk(self._music_path)]
        
    # Pickle folder list for next time.
    out_file = open(self._config_path, 'wb')
    cPickle.dump({self._music_path: folders}, out_file, protocol=2)
    return folders

  def _get_folder(self, idx):
    return self._folders[idx % len(self._folders)]

  def _get_new_folders(self, num, start_idx, step=1):
    folders = []
    idx = start_idx
    while len(folders) < num:
      if self._is_displayable(self._get_folder(idx)):
        folders.append(idx)
      idx += step
    return sorted(folders)

  def _is_displayable(self, folder):
    return (self._filter in folder and
            self._has_folder_image(folder) and
            self._includes_music(folder))

  def _has_folder_image(self, folder):
    cover_path = os.path.join(folder, self.cover_filename)
    return os.path.exists(cover_path)

  def _includes_music(self, folder):
    for file in os.listdir(folder):
      for extension in self.music_file_extensions:
        if file.endswith(extension):
          return True
    return False

  def _send_new_image_paths(self):
    image_paths = [os.path.join(self._get_folder(idx), self.cover_filename)
                   for idx in self._display_folders]
    pub.sendMessage("FOLDERS CHANGED", image_paths)

class JukeJointView(wx.Frame):
  def __init__(self, img_size, span):
    style = wx.STAY_ON_TOP | wx.FRAME_NO_TASKBAR | wx.NO_BORDER
    wx.Frame.__init__(self, None, -1, 'JukeJoint',
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

class JukeJointController(object):
  def __init__(self, music_path, config_path, player_path, img_size, span):
    self.model = JukeJointModel(span * span, music_path, config_path,
                                player_path)
    self.view = JukeJointView(img_size, span)
    self.img_size = img_size
    pub.subscribe(self._on_folders_changed, "FOLDERS CHANGED")

    self.view.panel.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
    for cover in self.view.panel.covers:
      cover.Bind(wx.EVT_LEFT_UP, self._on_left_click)
      cover.Bind(wx.EVT_RIGHT_UP, self._on_right_click)

    self.model.refresh_folders()
    self.view.Show()
    self.view.panel.SetFocus()

  def _on_folders_changed(self, message):
    images = []
    for image_path in message.data:
      image = wx.Image(image_path)
      image.Rescale(self.img_size, self.img_size, wx.IMAGE_QUALITY_HIGH)
      images.append(wx.BitmapFromImage(image))
    for cover, image in zip(self.view.panel.covers, images):
      cover.SetBitmap(image)

  def _on_key_down(self, event):
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

  def _on_left_click(self, event):
    cover_idx = self.view.panel.covers.index(event.GetEventObject())
    self.model.play(cover_idx)
    self.view.Destroy()

  def _on_right_click(self, event):
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
