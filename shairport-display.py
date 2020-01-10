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

    self.builder = Gtk.Builder()
    self.builder.add_from_file(os.path.dirname(os.path.realpath(__file__)) + "/shairport-display.glade")

    self.window = self.builder.get_object("Window")

    self.Art = self.builder.get_object("CoverArt")
    self.Title = self.builder.get_object("Title")
    self.Artist = self.builder.get_object("Artist")
    self.Album = self.builder.get_object("Album")

    self._initialize_display()

    self.window.show_all()
    self.window.fullscreen()

    self.window.connect("destroy", self.quit)
    self.window.connect("key-press-event", self._on_win_key_press_event)
    self.window.connect("window-state-event", self._on_window_state_event)

  def quit(self, *args):

    self.log.info("Stopping application")

    self.properties_changed.remove()
    Gtk.main_quit(args)

  def _setup_loop(self):

    self._loop = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

  def _setup_bus(self):

    dbus.set_default_main_loop(self._loop)

    if dbus.SystemBus().name_has_owner("org.gnome.ShairportSync"):
      self.log.warning("shairport-sync dbus service is running on the system bus")
      self._bus = dbus.SystemBus()
      return

    if dbus.SessionBus().name_has_owner("org.gnome.ShairportSync"):
      self.log.warning("shairport-sync dbus service is running on the session bus")
      self._bus = dbus.SessionBus()
      return

    self.log.error("shairport-sync dbus service is not running")
    client.quit()

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

    result = self._bus.call_blocking("org.gnome.ShairportSync", "/org/gnome/ShairportSync", "org.freedesktop.DBus.Properties", "Get", "ss", ["org.gnome.ShairportSync.RemoteControl", "Metadata"])

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

    self.properties_changed = self._bus.add_signal_receiver(handler_function=self.display_metadata,
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

    self.log.info("length: %s", str(datetime.timedelta(microseconds=metadata["length"])))

  def display_metadata(self, *args, **kwargs):

    interface = args[0]
    data = args[1]

    self.log.debug("Recieved signal for %s", interface)

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
      elapsed, remaining, total = data['ProgressString'].split('/')

      self.log.debug("elapsed: %d", int(elapsed))
      self.log.debug("remaining: %d", int(remaining))
      self.log.debug("total: %d", int(total))

    if 'PlayerState' in data:
      self.log.info("PlayerState: %s", data['PlayerState'])

if (__name__ == "__main__"):

  Gtk.init(None)

  client = ShairportSyncClient()
  signal.signal(signal.SIGINT, lambda *args: client.quit())

  Gtk.main()
