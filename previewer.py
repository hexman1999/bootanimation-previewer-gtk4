#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import zipfile
import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GLib, Gio, Gtk, Gdk, GdkPixbuf, Adw
import cv2
import numpy

# Initialize Libadwaita
Adw.init()


def pixbuf_to_surface(pixbuf):
    """Convert a GdkPixbuf to a cairo.ImageSurface (avoids deprecated Gdk.cairo_set_source_pixbuf)."""
    w = pixbuf.get_width()
    h = pixbuf.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.paint()
    surface.flush()
    return surface

DEVICE_PRESETS = [
    {"name": "Original Animation", "width": None, "height": None},
    {"name": "Phone (1080 × 2400) - 20:9 (Default)", "width": 1080, "height": 2400},
    {"name": "Phone (1080 × 1920) - 16:9", "width": 1080, "height": 1920},
    {"name": "Phone (1440 × 3200) - 20:9", "width": 1440, "height": 3200},
    {"name": "Phone (720 × 1280) - 16:9", "width": 720, "height": 1280},
    {"name": "Tablet (2560 × 1600) - 16:10", "width": 2560, "height": 1600},
    {"name": "Tablet (2048 × 1536) - 4:3", "width": 2048, "height": 1536},
    {"name": "Smartwatch (450 × 450) - Round 1:1", "width": 450, "height": 450},
    {"name": "Foldable Open (2208 × 1768) - 5:4", "width": 2208, "height": 1768},
    {"name": "Foldable Closed (840 × 2260) - 24:9", "width": 840, "height": 2260},
    {"name": "Custom Dimensions", "width": -1, "height": -1},
]

class BootAnimation:
    """Parses and manages a bootanimation.zip file."""
    def __init__(self, filepath):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.zip_file = zipfile.ZipFile(filepath, 'r')
        
        self.width = 0
        self.height = 0
        self.fps = 30
        self.parts = []
        self._frame_cache = {}
        self._surface_cache = {}
        
        # Validate the zip contains desc.txt
        if 'desc.txt' not in self.zip_file.namelist():
            self.zip_file.close()
            raise ValueError(f"'{self.filename}' is not a valid boot animation: missing desc.txt")
        
        self.parse_desc()
        self.load_parts_frames()

    def parse_desc(self):
        try:
            with self.zip_file.open('desc.txt', 'r') as f:
                desc_content = f.read().decode('utf-8')
            
            lines = desc_content.splitlines()
            if not lines:
                return

            # Parse header: width height fps [clock]
            header = lines[0].strip().split()
            if len(header) >= 3:
                self.width = int(header[0])
                self.height = int(header[1])
                self.fps = int(header[2])

            # Parse parts
            for line in lines[1:]:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) >= 4:
                    p_type = parts[0]  # 'p' or 'c'
                    count = int(parts[1])
                    pause = int(parts[2])
                    path = parts[3]
                    
                    bg_color = None
                    if len(parts) > 4:
                        bg_color = parts[4]
                        
                    self.parts.append({
                        'type': p_type,
                        'count': count,
                        'pause': pause,
                        'path': path,
                        'bg_color': bg_color,
                        'frames': [],
                        'trims': []
                    })
        except Exception as e:
            print(f"Error parsing desc.txt: {e}")

    def load_parts_frames(self):
        namelist = self.zip_file.namelist()
        
        for part in self.parts:
            path_prefix = part['path'].rstrip('/') + '/'
            
            frames = []
            for name in namelist:
                if name.startswith(path_prefix) and name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    frames.append(name)
            
            frames.sort()
            part['frames'] = frames
            
            trim_file = path_prefix + 'trim.txt'
            trims = []
            if trim_file in namelist:
                try:
                    with self.zip_file.open(trim_file) as f:
                        trim_lines = f.read().decode('utf-8').splitlines()
                    
                    for line in trim_lines:
                        line = line.strip()
                        if not line:
                            continue
                        match = re.match(r'(\d+)x(\d+)([-+]\d+)([-+]\d+)', line)
                        if match:
                            w, h, x, y = match.groups()
                            trims.append({
                                'w': int(w),
                                'h': int(h),
                                'x': int(x),
                                'y': int(y)
                            })
                except Exception as e:
                    print(f"Error parsing trim.txt in {part['path']}: {e}")
            
            part['trims'] = trims

    def get_frame_surface(self, part_index, frame_index):
        """Returns a (cairo.ImageSurface, pixbuf_width, pixbuf_height) tuple for the given frame."""
        key = (part_index, frame_index)
        if key in self._surface_cache:
            return self._surface_cache[key]
        
        if part_index >= len(self.parts):
            return None
        part = self.parts[part_index]
        
        if frame_index >= len(part['frames']):
            return None
        frame_file = part['frames'][frame_index]
        
        try:
            with self.zip_file.open(frame_file) as f:
                img_data = f.read()
            gbytes = GLib.Bytes.new(img_data)
            stream = Gio.MemoryInputStream.new_from_bytes(gbytes)
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
            surface = pixbuf_to_surface(pixbuf)
            result = (surface, pixbuf.get_width(), pixbuf.get_height())
            
            self._surface_cache[key] = result
            return result
        except Exception as e:
            print(f"Error loading frame {frame_file}: {e}")
            return None

    def get_total_frames(self):
        return sum(len(p['frames']) for p in self.parts)

    def close(self):
        self.zip_file.close()


class BootAnimationPreviewerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.antigravity.bootanimation_previewer",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        
        self.animation = None
        self.playing = False
        self.timer_id = None
        self.speed_multiplier = 1.0
        self.loop_entire = True
        
        # Infinite part loop limit configuration
        self.infinite_part_loop_limit = 5
        
        # Selected Device Preset index (default to index 1: Phone 1080 x 2400)
        self.selected_preset_index = 1
        
        # Playback state
        self.current_part_index = 0
        self.current_frame_index = 0
        self.current_part_play_count = 0
        self.pause_remaining_frames = 0
        
        self.workspace_dir = "/home/muhammad/Desktop/bootanimation previewer antigravity"

    def do_activate(self):
        self.build_ui()
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)

    def build_ui(self):
        # Main Window
        self.window = Adw.ApplicationWindow(application=self, title="Boot Animation Previewer")
        self.window.set_default_size(1080, 750)

        # Overlay Split View to allow sidebar resizing
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_min_sidebar_width(280)
        self.split_view.set_max_sidebar_width(400)
        self.split_view.set_sidebar_width_fraction(0.3)
        self.split_view.set_show_sidebar(True)
        self.split_view.set_pin_sidebar(True)
        self.window.set_content(self.split_view)

        # Sidebar Content
        self.build_sidebar()
        
        # Main Content Preview Area
        self.build_content_area()

        self.window.present()

    def build_sidebar(self):
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar_box.add_css_class("background")
        self.split_view.set_sidebar(sidebar_box)

        # Sidebar Header
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_box.append(sidebar_header)

        # Scrolled view for sidebar metadata/options
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        sidebar_box.append(scrolled)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        scrolled.set_child(vbox)

        # Custom Dimensions Group (Visible only when "Custom Dimensions" preset is selected)
        self.custom_dim_group = Adw.PreferencesGroup(title="Custom Viewport Dimensions")
        self.custom_dim_group.set_visible(False)
        vbox.append(self.custom_dim_group)

        # Custom Width
        adj_w = Gtk.Adjustment.new(1080.0, 100.0, 8000.0, 10.0, 100.0, 0.0)
        self.custom_w_spin = Gtk.SpinButton(adjustment=adj_w, climb_rate=10.0, digits=0)
        self.custom_w_spin.set_valign(Gtk.Align.CENTER)
        self.custom_w_spin.connect("value-changed", self.on_custom_dim_changed)
        
        custom_w_row = Adw.ActionRow(title="Width (px)")
        custom_w_row.add_suffix(self.custom_w_spin)
        self.custom_dim_group.add(custom_w_row)

        # Custom Height
        adj_h = Gtk.Adjustment.new(2400.0, 100.0, 8000.0, 10.0, 100.0, 0.0)
        self.custom_h_spin = Gtk.SpinButton(adjustment=adj_h, climb_rate=10.0, digits=0)
        self.custom_h_spin.set_valign(Gtk.Align.CENTER)
        self.custom_h_spin.connect("value-changed", self.on_custom_dim_changed)
        
        custom_h_row = Adw.ActionRow(title="Height (px)")
        custom_h_row.add_suffix(self.custom_h_spin)
        self.custom_dim_group.add(custom_h_row)

        # Playback Limits Group
        playback_group = Adw.PreferencesGroup(title="Playback Rules")
        vbox.append(playback_group)

        # Spin button to customize infinite loop parts repetitions
        adj = Gtk.Adjustment.new(5.0, 1.0, 100.0, 1.0, 5.0, 0.0)
        self.loop_limit_spin = Gtk.SpinButton(adjustment=adj, climb_rate=1.0, digits=0)
        self.loop_limit_spin.set_valign(Gtk.Align.CENTER)
        self.loop_limit_spin.connect("value-changed", self.on_loop_limit_changed)

        loop_limit_row = Adw.ActionRow(title="Infinite Part Repetitions")
        loop_limit_row.set_subtitle("Default loops for parts with 0 count")
        loop_limit_row.add_suffix(self.loop_limit_spin)
        playback_group.add(loop_limit_row)

        # Metadata / Info Group
        self.info_group = Adw.PreferencesGroup(title="Animation Metadata")
        vbox.append(self.info_group)

        self.row_filename = Adw.ActionRow(title="File Name", subtitle="-")
        self.row_resolution = Adw.ActionRow(title="Resolution", subtitle="-")
        self.row_fps = Adw.ActionRow(title="Frame Rate", subtitle="-")
        self.row_parts = Adw.ActionRow(title="Total Parts", subtitle="-")
        self.row_frames = Adw.ActionRow(title="Total Frames", subtitle="-")

        self.info_group.add(self.row_filename)
        self.info_group.add(self.row_resolution)
        self.info_group.add(self.row_fps)
        self.info_group.add(self.row_parts)
        self.info_group.add(self.row_frames)

        # Player State Group
        state_group = Adw.PreferencesGroup(title="Live Player Status")
        vbox.append(state_group)

        self.row_current_part = Adw.ActionRow(title="Current Part", subtitle="-")
        self.row_current_frame = Adw.ActionRow(title="Current Frame", subtitle="-")
        state_group.add(self.row_current_part)
        state_group.add(self.row_current_frame)

    def build_content_area(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.split_view.set_content(main_box)

        # Main HeaderBar
        content_header = Adw.HeaderBar()
        main_box.append(content_header)

        # Toggle button to collapse/expand the sidebar
        sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        sidebar_toggle.set_active(True)
        sidebar_toggle.set_tooltip_text("Toggle Sidebar")
        sidebar_toggle.connect("toggled", lambda btn: self.split_view.set_show_sidebar(btn.get_active()))
        content_header.pack_start(sidebar_toggle)

        # Device Dimensions Selector in the title bar
        self.preset_combo = Gtk.DropDown.new_from_strings([p["name"] for p in DEVICE_PRESETS])
        self.preset_combo.set_selected(self.selected_preset_index)
        self.preset_combo.connect("notify::selected", self.on_preset_changed)
        self.preset_combo.set_tooltip_text("Select Device Frame Preset")
        content_header.pack_start(self.preset_combo)

        # "Open Animation" button
        open_btn = Gtk.Button()
        open_btn.add_css_class("suggested-action")
        
        btn_content = Adw.ButtonContent()
        btn_content.set_icon_name("document-open-symbolic")
        btn_content.set_label("Open Animation")
        open_btn.set_child(btn_content)
        
        open_btn.connect("clicked", self.on_open_file)
        content_header.pack_end(open_btn)

        # Export button
        export_btn = Gtk.Button()
        export_content = Adw.ButtonContent()
        export_content.set_icon_name("document-save-as-symbolic")
        export_content.set_label("Export")
        export_btn.set_child(export_content)
        export_btn.connect("clicked", self.on_export_clicked)
        content_header.pack_end(export_btn)

        # Canvas Preview Area Container
        canvas_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        canvas_container.set_vexpand(True)
        canvas_container.set_hexpand(True)
        canvas_container.add_css_class("view")
        main_box.append(canvas_container)

        # Simulated screen canvas
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_vexpand(True)
        self.drawing_area.set_hexpand(True)
        self.drawing_area.set_draw_func(self.on_draw)
        canvas_container.append(self.drawing_area)

        # Control Bar
        control_bar_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        control_bar_wrapper.set_margin_top(24)
        control_bar_wrapper.set_margin_bottom(28)
        canvas_container.append(control_bar_wrapper)

        control_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        control_bar.set_halign(Gtk.Align.CENTER)
        control_bar.set_margin_start(20)
        control_bar.set_margin_end(20)
        control_bar_wrapper.append(control_bar)
        
        # Circular Play/Pause button
        self.btn_play_pause = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.btn_play_pause.add_css_class("circular")
        self.btn_play_pause.add_css_class("suggested-action")
        self.btn_play_pause.connect("clicked", self.on_play_pause_clicked)
        control_bar.append(self.btn_play_pause)

        # Stop button
        btn_stop = Gtk.Button(icon_name="media-playback-stop-symbolic")
        btn_stop.add_css_class("circular")
        btn_stop.connect("clicked", self.on_stop_clicked)
        control_bar.append(btn_stop)

        # Prev frame button
        btn_prev = Gtk.Button(icon_name="go-previous-symbolic")
        btn_prev.add_css_class("circular")
        btn_prev.connect("clicked", self.on_prev_frame_clicked)
        control_bar.append(btn_prev)

        # Next frame button
        btn_next = Gtk.Button(icon_name="go-next-symbolic")
        btn_next.add_css_class("circular")
        btn_next.connect("clicked", self.on_next_frame_clicked)
        control_bar.append(btn_next)

        # Loop toggle
        self.btn_loop = Gtk.ToggleButton(icon_name="media-playlist-repeat-symbolic")
        self.btn_loop.add_css_class("circular")
        self.btn_loop.set_active(self.loop_entire)
        self.btn_loop.connect("toggled", self.on_loop_toggled)
        control_bar.append(self.btn_loop)

        # Speed selector
        self.speed_combo = Gtk.DropDown.new_from_strings(["0.5x Speed", "1.0x Speed", "1.5x Speed", "2.0x Speed"])
        self.speed_combo.set_selected(1)
        self.speed_combo.connect("notify::selected", self.on_speed_changed)
        control_bar.append(self.speed_combo)

    def load_animation(self, filepath):
        self.stop_playback()
        
        if self.animation:
            self.animation.close()
            self.animation = None

        try:
            self.animation = BootAnimation(filepath)
        except (ValueError, zipfile.BadZipFile, KeyError) as e:
            self.show_error_dialog("Invalid Boot Animation", str(e))
            self.drawing_area.queue_draw()
            return
        except Exception as e:
            self.show_error_dialog("Failed to Open File", str(e))
            self.drawing_area.queue_draw()
            return
        
        self.current_part_index = 0
        self.current_frame_index = 0
        self.current_part_play_count = 0
        self.pause_remaining_frames = 0
        
        self.row_filename.set_subtitle(self.animation.filename)
        self.row_resolution.set_subtitle(f"{self.animation.width} x {self.animation.height}")
        self.row_fps.set_subtitle(f"{self.animation.fps} FPS")
        self.row_parts.set_subtitle(str(len(self.animation.parts)))
        self.row_frames.set_subtitle(str(self.animation.get_total_frames()))

        self.update_playback_status_labels()
        self.drawing_area.queue_draw()
        self.start_playback()

    def show_error_dialog(self, title, message):
        """Show a modern Adwaita error dialog."""
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self.window)

    def update_playback_status_labels(self):
        if not self.animation or self.current_part_index >= len(self.animation.parts):
            self.row_current_part.set_subtitle("-")
            self.row_current_frame.set_subtitle("-")
            return
            
        part = self.animation.parts[self.current_part_index]
        effective_count = part['count'] if part['count'] > 0 else self.infinite_part_loop_limit
        self.row_current_part.set_subtitle(f"{part['path']} (Play {self.current_part_play_count + 1}/{effective_count})")
        self.row_current_frame.set_subtitle(f"{self.current_frame_index + 1} / {len(part['frames'])}")

    def on_draw(self, drawing_area, cr, width, height, user_data=None):
        cr.set_source_rgb(0.08, 0.08, 0.08)
        cr.paint()

        if not self.animation:
            return

        preset = DEVICE_PRESETS[self.selected_preset_index]
        
        if preset["name"] == "Custom Dimensions":
            dev_w = int(self.custom_w_spin.get_value())
            dev_h = int(self.custom_h_spin.get_value())
        elif preset["width"] is None or preset["height"] is None:
            dev_w = self.animation.width or 1080
            dev_h = self.animation.height or 1920
        else:
            dev_w = preset["width"]
            dev_h = preset["height"]

        scale_dev_x = width / dev_w
        scale_dev_y = height / dev_h
        scale_dev = min(scale_dev_x, scale_dev_y) * 0.92

        dev_disp_w = dev_w * scale_dev
        dev_disp_h = dev_h * scale_dev
        dev_x = (width - dev_disp_w) / 2
        dev_y = (height - dev_disp_h) / 2

        # Draw Bezel
        cr.save()
        cr.set_source_rgb(0.18, 0.18, 0.18)
        cr.set_line_width(8)
        cr.round_rectangle(dev_x - 4, dev_y - 4, dev_disp_w + 8, dev_disp_h + 8, 20, 20) if hasattr(cr, 'round_rectangle') else cr.rectangle(dev_x - 4, dev_y - 4, dev_disp_w + 8, dev_disp_h + 8)
        cr.stroke()
        cr.restore()

        # Clip device screen area
        cr.save()
        cr.rectangle(dev_x, dev_y, dev_disp_w, dev_disp_h)
        cr.clip()

        bg_r, bg_g, bg_b = 0.0, 0.0, 0.0
        if self.current_part_index < len(self.animation.parts):
            part = self.animation.parts[self.current_part_index]
            if part['bg_color']:
                bg_r, bg_g, bg_b = self.parse_color(part['bg_color'])

        cr.set_source_rgb(bg_r, bg_g, bg_b)
        cr.rectangle(dev_x, dev_y, dev_disp_w, dev_disp_h)
        cr.fill()

        # Render frame
        frame_data = self.animation.get_frame_surface(self.current_part_index, self.current_frame_index)
        if frame_data:
            surface, frame_w, frame_h = frame_data
            anim_w = self.animation.width or frame_w
            anim_h = self.animation.height or frame_h

            # Global Device Transform space
            cr.save()
            cr.translate(dev_x, dev_y)
            cr.scale(scale_dev, scale_dev)

            # The logical animation canvas is ALWAYS rendered centered inside the device screen at 1:1 scale.
            # This ensures higher-density screens (like 1440x3200) naturally render the animation physically smaller
            # compared to lower-density screens (like 1080x2400), and larger animations are cropped correctly.
            anim_x = (dev_w - anim_w) / 2
            anim_y = (dev_h - anim_h) / 2

            cr.save()
            cr.translate(anim_x, anim_y)

            part = self.animation.parts[self.current_part_index]
            
            if part['trims'] and self.current_frame_index < len(part['trims']):
                trim = part['trims'][self.current_frame_index]
                cr.set_source_surface(surface, trim['x'], trim['y'])
                cr.paint()
            else:
                # Stretch untrimmed files to the logical animation canvas
                frame_scale_x = anim_w / frame_w
                frame_scale_y = anim_h / frame_h
                
                cr.save()
                cr.scale(frame_scale_x, frame_scale_y)
                cr.set_source_surface(surface, 0, 0)
                cr.paint()
                cr.restore()

            cr.restore()
            cr.restore()

        cr.restore()

    def parse_color(self, hex_str):
        if not hex_str:
            return 0.0, 0.0, 0.0
        hex_str = hex_str.strip()
        if hex_str.startswith('#'):
            hex_str = hex_str[1:]
        try:
            if len(hex_str) == 6:
                r = int(hex_str[0:2], 16) / 255.0
                r = int(hex_str[0:2], 16) / 255.0
                g = int(hex_str[2:4], 16) / 255.0
                b = int(hex_str[4:6], 16) / 255.0
                return r, g, b
            elif len(hex_str) == 3:
                r = int(hex_str[0] * 2, 16) / 255.0
                g = int(hex_str[1] * 2, 16) / 255.0
                b = int(hex_str[2] * 2, 16) / 255.0
                return r, g, b
        except ValueError:
            pass
        return 0.0, 0.0, 0.0

    def start_playback(self):
        if self.playing:
            return
        if not self.animation:
            return

        if self._is_at_end():
            self.current_part_index = 0
            self.current_frame_index = 0
            self.current_part_play_count = 0
            self.pause_remaining_frames = 0
            self.update_playback_status_labels()
            self.drawing_area.queue_draw()

        self.playing = True
        self.btn_play_pause.set_icon_name("media-playback-pause-symbolic")

        fps = self.animation.fps or 30
        interval = int(1000 / (fps * self.speed_multiplier))
        self.timer_id = GLib.timeout_add(interval, self.on_tick)

    def _is_at_end(self):
        if not self.animation or not self.animation.parts:
            return True
        last_idx = len(self.animation.parts) - 1
        if self.current_part_index < last_idx:
            return False
        if self.current_frame_index < len(self.animation.parts[-1]['frames']) - 1:
            return False
        return True

    def stop_playback(self):
        self.playing = False
        self.btn_play_pause.set_icon_name("media-playback-start-symbolic")
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def on_tick(self):
        if not self.playing:
            self.timer_id = None
            return False
            
        self.advance_frame()
        self.drawing_area.queue_draw()
        self.update_playback_status_labels()
        return True

    def advance_frame(self):
        if not self.animation or not self.animation.parts:
            return

        part = self.animation.parts[self.current_part_index]
        total_frames = len(part['frames'])

        if total_frames == 0:
            self.next_part()
            return

        if self.pause_remaining_frames > 0:
            self.pause_remaining_frames -= 1
            if self.pause_remaining_frames == 0:
                self.complete_part_play(part)
            return

        self.current_frame_index += 1
        if self.current_frame_index >= total_frames:
            self.current_frame_index = total_frames - 1
            if part['pause'] > 0:
                self.pause_remaining_frames = part['pause']
            else:
                self.complete_part_play(part)

    def complete_part_play(self, part):
        self.current_part_play_count += 1
        
        effective_count = part['count']
        if effective_count == 0:
            effective_count = self.infinite_part_loop_limit
            
        if self.current_part_play_count < effective_count:
            self.current_frame_index = 0
            self.pause_remaining_frames = 0
        else:
            self.next_part()

    def next_part(self):
        self.current_part_index += 1
        self.current_frame_index = 0
        self.current_part_play_count = 0
        self.pause_remaining_frames = 0
        
        if self.current_part_index >= len(self.animation.parts):
            if self.loop_entire:
                self.current_part_index = 0
            else:
                self.stop_playback()
                self.current_part_index = len(self.animation.parts) - 1
                self.current_frame_index = len(self.animation.parts[-1]['frames']) - 1

    # Callbacks
    def on_play_pause_clicked(self, btn):
        if self.playing:
            self.stop_playback()
        else:
            self.start_playback()

    def on_stop_clicked(self, btn):
        self.stop_playback()
        self.current_part_index = 0
        self.current_frame_index = 0
        self.current_part_play_count = 0
        self.pause_remaining_frames = 0
        self.update_playback_status_labels()
        self.drawing_area.queue_draw()

    def on_prev_frame_clicked(self, btn):
        self.stop_playback()
        if not self.animation:
            return
            
        self.current_frame_index -= 1
        if self.current_frame_index < 0:
            self.current_part_index -= 1
            if self.current_part_index < 0:
                self.current_part_index = len(self.animation.parts) - 1
            part = self.animation.parts[self.current_part_index]
            self.current_frame_index = len(part['frames']) - 1
            
        self.update_playback_status_labels()
        self.drawing_area.queue_draw()

    def on_next_frame_clicked(self, btn):
        self.stop_playback()
        if not self.animation:
            return
            
        part = self.animation.parts[self.current_part_index]
        self.current_frame_index += 1
        if self.current_frame_index >= len(part['frames']):
            self.current_part_index += 1
            if self.current_part_index >= len(self.animation.parts):
                self.current_part_index = 0
            self.current_frame_index = 0
            
        self.update_playback_status_labels()
        self.drawing_area.queue_draw()

    def on_loop_toggled(self, btn):
        self.loop_entire = btn.get_active()

    def on_speed_changed(self, combo, pspec):
        selected = combo.get_selected()
        speeds = [0.5, 1.0, 1.5, 2.0]
        if selected < len(speeds):
            self.speed_multiplier = speeds[selected]
            if self.playing:
                self.stop_playback()
                self.start_playback()

    def on_preset_changed(self, combo, pspec):
        self.selected_preset_index = combo.get_selected()
        preset = DEVICE_PRESETS[self.selected_preset_index]
        
        is_custom = (preset["name"] == "Custom Dimensions")
        self.custom_dim_group.set_visible(is_custom)
        self.drawing_area.queue_draw()

    def on_custom_dim_changed(self, spin):
        self.drawing_area.queue_draw()

    def on_loop_limit_changed(self, spin):
        self.infinite_part_loop_limit = int(spin.get_value())
        self.update_playback_status_labels()

    def on_open_file(self, btn):
        dialog = Gtk.FileDialog(title="Open Boot Animation Zip")
        
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Boot Animation ZIP files")
        file_filter.add_pattern("*.zip")
        
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        
        dialog.open(self.window, None, self.on_file_selected)

    def on_file_selected(self, dialog, result):
        try:
            file_info = dialog.open_finish(result)
            if file_info:
                filepath = file_info.get_path()
                self.load_animation(filepath)
        except Exception as e:
            print(f"Error selecting file: {e}")

    def render_frame_to_surface(self, part_index, frame_index, dev_w, dev_h):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, dev_w, dev_h)
        cr = cairo.Context(surface)

        bg_r, bg_g, bg_b = 0.0, 0.0, 0.0
        if part_index < len(self.animation.parts):
            part = self.animation.parts[part_index]
            if part['bg_color']:
                bg_r, bg_g, bg_b = self.parse_color(part['bg_color'])
        cr.set_source_rgb(bg_r, bg_g, bg_b)
        cr.paint()

        frame_data = self.animation.get_frame_surface(part_index, frame_index)
        if frame_data:
            surface_f, frame_w, frame_h = frame_data
            anim_w = self.animation.width or frame_w
            anim_h = self.animation.height or frame_h

            anim_x = (dev_w - anim_w) / 2
            anim_y = (dev_h - anim_h) / 2

            cr.save()
            cr.translate(anim_x, anim_y)

            part = self.animation.parts[part_index]
            if part['trims'] and frame_index < len(part['trims']):
                trim = part['trims'][frame_index]
                cr.set_source_surface(surface_f, trim['x'], trim['y'])
                cr.paint()
            else:
                frame_scale_x = anim_w / frame_w
                frame_scale_y = anim_h / frame_h
                cr.save()
                cr.scale(frame_scale_x, frame_scale_y)
                cr.set_source_surface(surface_f, 0, 0)
                cr.paint()
                cr.restore()

            cr.restore()

        surface.flush()
        return surface

    def _render_frame_to_array(self, part_idx, frame_idx, dev_w, dev_h):
        surface = self.render_frame_to_surface(part_idx, frame_idx, dev_w, dev_h)
        return self.surface_to_numpy_rgb(surface)

    def surface_to_numpy_rgb(self, surface):
        data = surface.get_data()
        arr = numpy.frombuffer(data, dtype=numpy.uint8).reshape((surface.get_height(), surface.get_width(), 4))
        r = arr[:, :, 2].copy()
        g = arr[:, :, 1].copy()
        b = arr[:, :, 0].copy()
        return numpy.stack([r, g, b], axis=2)

    def on_export_clicked(self, btn):
        if not self.animation:
            self.show_error_dialog("No Animation", "Open a boot animation first.")
            return

        dialog = Gtk.FileDialog(title="Export Animation")

        mp4_filter = Gtk.FileFilter()
        mp4_filter.set_name("MP4 Video (*.mp4)")
        mp4_filter.add_pattern("*.mp4")

        gif_filter = Gtk.FileFilter()
        gif_filter.set_name("GIF Image (*.gif)")
        gif_filter.add_pattern("*.gif")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(mp4_filter)
        filters.append(gif_filter)
        dialog.set_filters(filters)

        basename = os.path.splitext(self.animation.filename)[0]
        dialog.set_initial_name(f"{basename}.mp4")

        dialog.save(self.window, None, self.on_export_file_selected)

    def on_export_file_selected(self, dialog, result):
        try:
            file_info = dialog.save_finish(result)
            if not file_info:
                return
            filepath = file_info.get_path()
            self.do_export(filepath)
        except Exception as e:
            self.show_error_dialog("Export Error", f"Failed to save file: {e}")

    def do_export(self, filepath):
        if not self.animation:
            return

        self.stop_playback()

        preset = DEVICE_PRESETS[self.selected_preset_index]
        if preset["name"] == "Custom Dimensions":
            dev_w = int(self.custom_w_spin.get_value())
            dev_h = int(self.custom_h_spin.get_value())
        elif preset["width"] is None or preset["height"] is None:
            dev_w = self.animation.width or 1080
            dev_h = self.animation.height or 1920
        else:
            dev_w = preset["width"]
            dev_h = preset["height"]

        fps = self.animation.fps or 30
        ext = os.path.splitext(filepath)[1].lower()

        frames = self._get_export_frame_list()

        if not frames:
            self.show_error_dialog("Export Error", "No frames to export.")
            return

        state = {
            'filepath': filepath,
            'frames': frames,
            'dev_w': dev_w,
            'dev_h': dev_h,
            'fps': fps,
            'ext': ext,
            'idx': 0,
            'total': len(frames),
        }

        import tempfile
        fd, tmp_mp4 = tempfile.mkstemp(suffix='.mp4')
        os.close(fd)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(tmp_mp4, fourcc, fps, (dev_w, dev_h))
        state['tmp_mp4'] = tmp_mp4
        state['writer'] = writer

        n_workers = max(1, os.cpu_count() - 1)
        executor = ThreadPoolExecutor(max_workers=n_workers)
        futures = []
        for part_idx, frame_idx in frames:
            futures.append(executor.submit(self._render_frame_to_array, part_idx, frame_idx, dev_w, dev_h))
        state['executor'] = executor
        state['futures'] = futures
        state['next_to_write'] = 0

        self._export_state = state

        export_dialog = Adw.AlertDialog(
            heading="Exporting Animation",
            body=f"Rendering {len(frames)} frames at {dev_w}\u00d7{dev_h}..."
        )
        export_dialog.add_response("cancel", "Cancel")
        export_dialog.connect("response", self._on_export_dialog_response)
        export_dialog.present(self.window)
        self._export_dialog = export_dialog

        GLib.idle_add(self._export_process_batch)

    def _get_export_frame_list(self):
        frames = []
        part_index = 0
        frame_index = 0
        part_play_count = 0
        pause_remaining = 0

        while part_index < len(self.animation.parts):
            part = self.animation.parts[part_index]
            total_frames = len(part['frames'])

            if total_frames == 0:
                part_index += 1
                continue

            frames.append((part_index, frame_index))

            if pause_remaining > 0:
                pause_remaining -= 1
                if pause_remaining == 0:
                    part_play_count += 1
                    effective_count = part['count'] if part['count'] > 0 else self.infinite_part_loop_limit
                    if part_play_count < effective_count:
                        frame_index = 0
                    else:
                        part_index += 1
                        frame_index = 0
                        part_play_count = 0
            else:
                frame_index += 1
                if frame_index >= total_frames:
                    frame_index = total_frames - 1
                    if part['pause'] > 0:
                        pause_remaining = part['pause']
                    else:
                        part_play_count += 1
                        effective_count = part['count'] if part['count'] > 0 else self.infinite_part_loop_limit
                        if part_play_count < effective_count:
                            frame_index = 0
                        else:
                            part_index += 1
                            frame_index = 0
                            part_play_count = 0

        return frames

    def _on_export_dialog_response(self, dialog, response):
        if response == "cancel":
            self._export_state['cancelled'] = True

    def _export_process_batch(self):
        state = self._export_state
        futures = state['futures']
        batch_size = 30

        try:
            written = 0
            for _ in range(batch_size):
                if state.get('cancelled'):
                    state['executor'].shutdown(wait=False)
                    self._abort_export_writer()
                    self._finish_export(cancelled=True)
                    return False

                ntw = state['next_to_write']
                if ntw >= state['total']:
                    break

                future = futures[ntw]
                if not future.done():
                    break

                rgb = future.result()
                futures[ntw] = None
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                state['writer'].write(bgr)
                state['next_to_write'] = ntw + 1
                written += 1

            if state['next_to_write'] < state['total']:
                if self._export_dialog and written > 0:
                    self._export_dialog.set_body(f"Rendered {state['next_to_write']}/{state['total']} frames...")
                return True

            state['executor'].shutdown(wait=False)
            self._finish_export(encode=True)
        except Exception as e:
            state['executor'].shutdown(wait=False)
            self._abort_export_writer()
            self._finish_export(error=str(e))

        return False

    def _abort_export_writer(self):
        state = self._export_state
        if 'writer' in state:
            state['writer'].release()

    def _finish_export(self, encode=False, error=None, cancelled=False):
        if cancelled:
            if self._export_dialog:
                self._export_dialog.close()
            self.show_error_dialog("Export Cancelled", "Export was cancelled.")
            self._cleanup_export()
            return

        if error:
            if self._export_dialog:
                self._export_dialog.close()
            self.show_error_dialog("Export Failed", error)
            self._cleanup_export()
            return

        if encode:
            self._export_encode()

    def _export_encode(self):
        state = self._export_state
        ext = state['ext']
        frame_count = state['total']

        if self._export_dialog:
            self._export_dialog.set_body("Encoding video...")

        try:
            if ext == '.gif':
                state['writer'].release()
                palette_path = state['tmp_mp4'] + '.png'
                subprocess.run([
                    'ffmpeg', '-y',
                    '-i', state['tmp_mp4'],
                    '-vf', 'palettegen=max_colors=256:stats_mode=diff',
                    '-threads', '0',
                    palette_path,
                    '-loglevel', 'error'
                ], check=True, capture_output=True)
                subprocess.run([
                    'ffmpeg', '-y',
                    '-i', state['tmp_mp4'],
                    '-i', palette_path,
                    '-lavfi', 'paletteuse=dither=bayer:bayer_scale=5',
                    '-threads', '0',
                    '-loop', '0',
                    state['filepath'],
                    '-loglevel', 'error'
                ], check=True, capture_output=True)
            elif ext == '.mp4':
                state['writer'].release()
                shutil.move(state['tmp_mp4'], state['filepath'])
            else:
                raise ValueError(f"Unsupported format: {ext}")

            if self._export_dialog:
                self._export_dialog.close()
            self.show_success_dialog(
                "Export Complete",
                f"Exported {frame_count} frames to {os.path.basename(state['filepath'])}"
            )
        except subprocess.CalledProcessError as e:
            msg = e.stderr.decode() if e.stderr else str(e)
            if self._export_dialog:
                self._export_dialog.close()
            self.show_error_dialog("Export Failed", f"ffmpeg error: {msg[:500]}")
        except Exception as e:
            if self._export_dialog:
                self._export_dialog.close()
            self.show_error_dialog("Export Failed", str(e))
        finally:
            self._cleanup_export()

    def _cleanup_export(self):
        if hasattr(self, '_export_state') and self._export_state:
            executor = self._export_state.get('executor')
            if executor:
                executor.shutdown(wait=False)
            tmp = self._export_state.get('tmp_mp4')
            if tmp:
                palette = tmp + '.png'
                if os.path.exists(palette):
                    os.unlink(palette)
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._export_state = {}
        self._export_dialog = None

    def show_success_dialog(self, title, message):
        dialog = Adw.AlertDialog(heading=title, body=message)
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self.window)


if __name__ == "__main__":
    app = BootAnimationPreviewerApp()
    try:
        sys.exit(app.run(sys.argv))
    except KeyboardInterrupt:
        print("\nExiting application.")