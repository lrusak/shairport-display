#!/usr/bin/env /usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GdkPixbuf

import dbus
import dbus.mainloop.glib
import datetime
import signal
import sys
import os
import time
import logging

class ShairportSyncClient(object):

  def __init__(self):

    self.log = logging.getLogger("shairport-display")

    self.format = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', "%Y-%m-%d %H:%M:%S")

    self.handler = logging.StreamHandler(stream=sys.stdout)
    self.handler.setFormatter(self.format)
    self.handler.setLevel(logging.DEBUG)

    self.log.addHandler(self.handler)
    self.log.setLevel(logging.DEBUG)

    self.log.info("Starting application")

    self.properties_changed = None

    self._setup_loop()
    self._setup_bus()
    self._setup_signals()

    self.length = 0
    self.fraction = 0.0
    self.duration = 500 # miliseconds
    self.timer = None

    self.builder = Gtk.Builder()
    self.builder.add_from_file(os.path.dirname(os.path.realpath(__file__)) + "/shairport-display.glade")

    self.window = self.builder.get_object("Window")

    geometry = Gdk.Geometry()
    geometry.min_width = 800
    geometry.max_width = 800
    geometry.min_height = 480
    geometry.max_height = 480

    hints = Gdk.WindowHints(Gdk.WindowHints.MAX_SIZE | Gdk.WindowHints.MIN_SIZE)

    self.window.set_geometry_hints(None, geometry, hints)

    self.Art = self.builder.get_object("CoverArt")
    self.Title = self.builder.get_object("Title")
    self.Artist = self.builder.get_object("Artist")
    self.Album = self.builder.get_object("Album")

    self.Elapsed = self.builder.get_object("Elapsed")
    self.Remaining = self.builder.get_object("Remaining")
    self.ProgressBar = self.builder.get_object("ProgressBar")

    self.window.show_all()
    self.window.fullscreen()

    self._clear_display()
    self._initialize_display()

    self.window.connect("destroy", self.quit)
    self.window.connect("key-press-event", self._on_win_key_press_event)
    self.window.connect("window-state-event", self._on_window_state_event)

  def _tickEvent(self):

    if self.length != 0:
      self.fraction += self.duration / 1000 / self.length

      #self.log.debug("elapsed: %s", str(datetime.timedelta(seconds=round(self.length * self.fraction))))

      self.ProgressBar.set_fraction(self.fraction)

      elapsed = round(self.length * self.fraction)

      elapsed_time = datetime.timedelta(seconds=elapsed)
      remaining_time = datetime.timedelta(seconds=self.length - elapsed)

      elapsed_formated = ':'.join(str(elapsed_time).split(':')[1:])
      remaining_formated = ':'.join(str(remaining_time).split(':')[1:])

      self.Elapsed.set_text(elapsed_formated)
      self.Remaining.set_text("-" + remaining_formated)

    return True

  def quit(self, *args):

    self.log.info("Stopping application")

    self.properties_changed.remove()

    Gtk.main_quit(args)

  def _setup_loop(self):

    self._loop = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

  def _setup_bus(self):

    dbus.set_default_main_loop(self._loop)

    if dbus.SystemBus().name_has_owner("org.gnome.ShairportSync"):
      self.log.debug("shairport-sync dbus service is running on the system bus")
      self._bus = dbus.SystemBus()
      return

    if dbus.SessionBus().name_has_owner("org.gnome.ShairportSync"):
      self.log.debug("shairport-sync dbus service is running on the session bus")
      self._bus = dbus.SessionBus()
      return

    self.log.error("shairport-sync dbus service is not running")
    exit(1)

  def _fullscreen_mode(self):

    if self._is_fullscreen:
      self.window.unfullscreen()
    else:
      self.window.fullscreen()

  def _on_win_key_press_event(self, widget, ev):

    key = Gdk.keyval_name(ev.keyval)
    if key == "f":
      self._fullscreen_mode()
    if key == "q":
      self.quit()

  def _on_window_state_event(self, widget, ev):
    self._is_fullscreen = bool(ev.new_window_state & Gdk.WindowState.FULLSCREEN)

  def _initialize_display(self):

    try:
      result = self._bus.call_blocking("org.gnome.ShairportSync", "/org/gnome/ShairportSync", "org.freedesktop.DBus.Properties", "Get", "ss", ["org.gnome.ShairportSync.RemoteControl", "Metadata"])
    except dbus.exceptions.DBusException:
      self.log.warning("shairport-sync is not running on the bus")
      return

    try:
      metadata = { "art" : result['mpris:artUrl'].split("://")[-1],
                   "title" : result['xesam:title'],
                   "artist" : ", ".join(result['xesam:artist']),
                   "album" : result['xesam:album'],
                   "length" : result['mpris:length'],
                 }

    except KeyError:
      self.log.warning("no metadata available to initialize the display")
      return

    self._set_metadata(metadata)

  def _setup_signals(self):

    self.properties_changed = self._bus.add_signal_receiver(handler_function=self._display_metadata,
                                                            signal_name='PropertiesChanged',
                                                            dbus_interface='org.freedesktop.DBus.Properties',
                                                            bus_name='org.gnome.ShairportSync',
                                                            member_keyword='signal')

  def _set_metadata(self, metadata):

    self.log.debug("Metadata available")

    for key in metadata:
      self.log.info("%s: %s", key, metadata[key])

    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(metadata["art"], 380, -1, True)
    self.Art.set_from_pixbuf(pixbuf)
    self.Title.set_text(metadata["title"])
    self.Artist.set_text(metadata["artist"])
    self.Album.set_text(metadata["album"])
    self.ProgressBar.show()
    self.Elapsed.show()
    self.Remaining.show()

    self.log.info("length: %s", str(datetime.timedelta(microseconds=metadata["length"])))

  def _stop_timer(self):

    if self.timer is not None:
      self.log.debug("stopping timer")
      GLib.source_remove(self.timer)

  def _start_timer(self):

    if self.timer is not None:
      self.log.debug("stopping stale timer")
      GLib.source_remove(self.timer)

    self.log.debug("starting timer")
    self.timer = GLib.timeout_add(self.duration, self._tickEvent)

  def _clear_display(self):
    self.Art.clear()
    self.Title.set_text("")
    self.Artist.set_text("")
    self.Album.set_text("")
    self.ProgressBar.hide()
    self.Elapsed.hide()
    self.Remaining.hide()

  def _display_metadata(self, *args, **kwargs):

    interface = args[0]
    data = args[1]

    self.log.debug("Recieved signal for %s", interface)

    if interface == "org.gnome.ShairportSync.RemoteControl":

      if 'Metadata' in data:

        try:
          metadata = { "art" : data['Metadata']['mpris:artUrl'].split("://")[-1],
                       "title" : data['Metadata']['xesam:title'],
                       "artist" : ', '.join(data['Metadata']['xesam:artist']),
                       "album" : data['Metadata']['xesam:album'],
                       "length" : data['Metadata']['mpris:length'],
                     }

        except KeyError:
          self.log.warning("no metadata available to initialize the display")
          return

        self._set_metadata(metadata)

      if 'ProgressString' in data:
        start, current, end = [int(x) for x in data['ProgressString'].split('/')]

        self.log.debug("start: %d", start)
        self.log.debug("current: %d", current)
        self.log.debug("end: %d", end)

        self.length = round((end - start) / 44100)
        elapsed = round((current - start) / 44100)

        self.log.debug("length: %s", str(datetime.timedelta(seconds=self.length)))
        self.log.debug("elapsed: %s", str(datetime.timedelta(seconds=elapsed)))

        self.fraction = elapsed / self.length

        self._start_timer()

      if 'PlayerState' in data:
        state = data['PlayerState']
        self.log.info("PlayerState: %s", state)

        if state == "Stopped":
          self._stop_timer()
        elif state == "Playing":
          self._start_timer()
        elif state == "Paused":
          pass

    if interface == "org.gnome.ShairportSync":

      if "Active" in data:
        if data["Active"]:
          self.log.info("device connected")
          self._initialize_display()
        else:
          self.log.info("device disconnected")
          self._clear_display()


if (__name__ == "__main__"):

  Gtk.init(None)

  client = ShairportSyncClient()
  signal.signal(signal.SIGINT, lambda *args: client.quit())

  Gtk.main()
