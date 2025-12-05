# SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import omni.ui as ui
import omni.kit.app
import omni.usd
import omni.kit.commands
import omni.kit.viewport.utility as vp_utility
from omni.kit.window.filepicker import FilePickerDialog
import omni.client  # [중요] Nucleus 파일 입출력을 위해 추가
from pxr import Usd, UsdGeom, Gf
import time
from datetime import datetime
import json
import os
import asyncio

class UIBuilder:
    def __init__(self):
        self.wrapped_ui_elements = []
        
        # UI Element References
        self._lbl_status = None
        self._lbl_count = None
        self._vstack_history = None
        self._field_duration = None
        self._field_filepath = None
        self._txt_log_field = None
        
        # File Picker
        self._file_picker = None
        
        # State
        self._is_recording = False
        self._is_playing = False
        self._recorded_data = [] 
        self._playback_index = 0
        self._playback_camera_path = ""
        self._current_cam_path = "/OmniverseKit_Persp"
        
        # Settings
        self._target_fps = 60.0
        self._record_interval = 1.0 / self._target_fps 
        self._last_record_time = 0.0
        self._auto_stop_frames = 0 
        self._recording_start_time = 0.0

        # FPS Measurement
        self._fps_history = [] 
        self._playback_start_time = 0.0
        self._played_frame_count = 0
        
        # Update Subscription
        self._update_sub = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update_event)
        
        print(f"Camera Recorder Initialized. Target FPS: {self._target_fps}")

    def cleanup(self):
        self._update_sub = None
        self._is_recording = False
        self._is_playing = False
        self._recorded_data = []
        self._lbl_status = None
        self._cleanup_playback_resources()
        if self._file_picker:
            self._file_picker.hide()
            self._file_picker = None

    def build_ui(self):
        with ui.VStack(spacing=2):
            self._create_status_ui()
            self._create_recorder_ui()

    def _create_status_ui(self):
        self._status_frame = ui.CollapsableFrame("System Log", collapsed=False, height=0)
        with self._status_frame:
            with ui.VStack(height=0, spacing=2, style={"margin": 2}):
                self._txt_log_field = ui.StringField(
                    multiline=True,
                    read_only=True,
                    height=85, 
                    style={"background_color": 0xFF222222, "font_size": 12, "color": 0xFFAAAAAA} 
                )
                self._log_message("System Ready.")

    def _create_recorder_ui(self):
        self._recorder_frame = ui.CollapsableFrame("Recorder Control", collapsed=False)
        with self._recorder_frame:
            with ui.VStack(height=0, spacing=4, style={"margin": 4}):
                
                # 1. Status Info
                with ui.HStack(height=20):
                    ui.Label("Status:", width=45, style={"color": 0xFFAAAAAA, "font_size": 14})
                    self._lbl_status = ui.Label("Ready", width=90, style={"color": 0xFFFFFFFF, "font_size": 14})
                    ui.Spacer(width=5)
                    ui.Label("Frames:", width=50, style={"color": 0xFFAAAAAA, "font_size": 14})
                    self._lbl_count = ui.Label("0", style={"color": 0xFFFFFFFF, "font_size": 14})

                ui.Separator(height=6)

                # 2. Controls
                with ui.HStack(height=24, spacing=4):
                    ui.Label("Auto-Stop:", width=65, tooltip="0=Manual", style={"font_size": 14})
                    self._field_duration = ui.FloatDrag(min=0, max=3600, step=0.5, width=45, style={"font_size": 14})
                    self._field_duration.model.set_value(0.0)
                    ui.Spacer(width=5)
                    ui.Button("Start", clicked_fn=self._on_rec_start, height=24, style={"background_color": 0xFF4444AA, "font_size": 14})
                    ui.Button("Stop", clicked_fn=self._on_rec_stop, width=55, height=24, style={"background_color": 0xFFAA4444, "font_size": 14})

                # 3. Playback
                with ui.HStack(height=24, spacing=4):
                    ui.Button("Play Recording", height=24, clicked_fn=self._on_rec_play, tooltip="Replay Synced", style={"font_size": 14})
                    ui.Button(
                        "Delete Cams", 
                        width=90,
                        height=24, 
                        clicked_fn=self._on_manual_delete, 
                        style={"background_color": 0xFF333333, "color": 0xFF5555FF, "font_size": 12},
                        tooltip="Delete all Recorded_Cam prims"
                    )

                ui.Separator(height=6)

                # 4. File I/O
                with ui.HStack(height=22, spacing=4):
                    ui.Label("File:", width=30, style={"font_size": 14})
                    
                    # 기본값 예시: omniverse://localhost/Users/test/camera_path.json 등으로 변경 가능
                    default_path = os.path.abspath("camera_path.json").replace("\\", "/")
                    self._field_filepath = ui.StringField(height=22, style={"font_size": 14})
                    self._field_filepath.model.set_value(default_path)
                    
                    ui.Button("Search", width=60, height=22, clicked_fn=self._on_open_file_picker, style={"font_size": 12})

                with ui.HStack(height=22, spacing=4):
                    ui.Button("Save JSON", height=22, clicked_fn=self._on_save_file, style={"font_size": 13})
                    ui.Button("Load JSON", height=22, clicked_fn=self._on_load_file, style={"font_size": 13})

                ui.Separator(height=6)
                
                # 5. History
                ui.Label("History (Last 5):", height=14, style={"color": 0xFF00AAFF, "font_size": 12})
                self._vstack_history = ui.VStack(spacing=2)

    # --- Log ---
    def _log_message(self, msg: str):
        if not self._txt_log_field: return
        timestamp = datetime.now().strftime("%H:%M:%S")
        current_text = self._txt_log_field.model.get_value_as_string()
        updated = f"{current_text}\n[{timestamp}] {msg}" if current_text else f"[{timestamp}] {msg}"
        self._txt_log_field.model.set_value(updated)

    # --- File Picker ---
    def _on_open_file_picker(self):
        if self._file_picker:
            self._file_picker.show()
            return
        self._file_picker = FilePickerDialog(
            "Select Camera Data File",
            allow_multi_selection=False,
            apply_button_label="Select",
            click_apply_handler=self._on_file_picked,
            item_filter_options=["JSON Files (*.json)"]
        )
        self._file_picker.show()

    def _on_file_picked(self, filename: str, dirname: str):
        if not filename: return
        # Omniverse 경로는 슬래시(/)를 사용합니다.
        full_path = f"{dirname}/{filename}".replace("\\", "/")
        self._field_filepath.model.set_value(full_path)
        self._file_picker.hide()
        self._log_message(f"Selected: {filename}")

    # --- Recorder Logic ---
    def _on_rec_start(self):
        if self._is_playing: self._cleanup_playback_resources()
        self._is_recording = True
        self._is_playing = False
        self._recorded_data = []
        self._last_record_time = 0.0
        
        duration = self._field_duration.model.get_value_as_float()
        if duration > 0:
            self._auto_stop_frames = int(duration * self._target_fps)
            self._recording_start_time = time.time()
            stop_msg = f"Auto: {int(duration)}s"
        else:
            self._auto_stop_frames = 0
            stop_msg = "Manual"
        
        self._log_message(f"Start Rec ({stop_msg})...")
        if self._lbl_status: self._lbl_status.text = f"🔴 Rec..."
        if self._lbl_count: self._lbl_count.text = "0"

    def _on_rec_stop(self):
        was_playing = self._is_playing
        if was_playing:
            self._finalize_fps_record()
            self._cleanup_playback_resources()

        if self._is_recording:
            self._log_message(f"Stopped. Captured {len(self._recorded_data)} f.")
        elif was_playing:
            self._log_message("Playback Stopped.")

        self._is_recording = False
        self._is_playing = False
        if self._lbl_status: self._lbl_status.text = "Stopped"

    def _on_rec_play(self):
        if not self._recorded_data:
            self._log_message("Error: No data.")
            if self._lbl_status: self._lbl_status.text = "⚠️ No Data"
            return
        self._cleanup_playback_resources()
        
        stage = omni.usd.get_context().get_stage()
        base_path = "/World/Recorded_Cam"
        self._playback_camera_path = omni.usd.get_stage_next_free_path(stage, base_path, False)
        new_cam_prim = UsdGeom.Camera.Define(stage, self._playback_camera_path)
        src_prim = stage.GetPrimAtPath("/OmniverseKit_Persp")
        if src_prim.IsValid(): self._copy_camera_attributes(src_prim, new_cam_prim.GetPrim())
        self._set_viewport_camera(self._playback_camera_path)
        
        self._is_playing = True
        self._is_recording = False
        self._playback_start_time = time.time()
        self._played_frame_count = 0
        self._log_message(f"Playing...")
        if self._lbl_status: self._lbl_status.text = "🟢 Playing..."

    def _on_manual_delete(self):
        self._cleanup_playback_resources()
        self._log_message("Deleted recorded cameras.")

    def _on_update_event(self, e):
        stage = omni.usd.get_context().get_stage()
        if not stage: return
        current_time = time.time()

        if self._is_recording:
            if current_time - self._last_record_time >= self._record_interval:
                cam_prim = stage.GetPrimAtPath("/OmniverseKit_Persp")
                if cam_prim.IsValid():
                    xform = UsdGeom.Xformable(cam_prim)
                    world = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    self._recorded_data.append({
                        "pos": world.ExtractTranslation(),
                        "rot": world.ExtractRotationQuat()
                    })
                    self._last_record_time = current_time
                    if self._lbl_count: self._lbl_count.text = str(len(self._recorded_data))
                    if self._auto_stop_frames > 0 and len(self._recorded_data) >= self._auto_stop_frames:
                        self._log_message("Auto-stop reached.")
                        self._on_rec_stop()

        elif self._is_playing:
            elapsed = current_time - self._playback_start_time
            float_idx = elapsed * self._target_fps
            idx0 = int(float_idx)
            idx1 = idx0 + 1
            t = float_idx - idx0

            if idx0 >= len(self._recorded_data) - 1:
                self._on_rec_stop()
                if self._lbl_status: self._lbl_status.text = "Done"
                self._log_message("Playback Done.")
                return

            data0 = self._recorded_data[idx0]
            data1 = self._recorded_data[idx1]
            interp_pos = Gf.Lerp(t, data0["pos"], data1["pos"])
            interp_rot = Gf.Slerp(t, data0["rot"], data1["rot"])

            cam_prim = stage.GetPrimAtPath(self._playback_camera_path)
            if cam_prim.IsValid():
                xform = UsdGeom.Xformable(cam_prim)
                mat = Gf.Matrix4d(Gf.Rotation(interp_rot), interp_pos)
                
                xform_op = None
                for op in xform.GetOrderedXformOps():
                    if op.GetOpType() == UsdGeom.XformOp.TypeTransform:
                        xform_op = op
                        break
                if not xform_op:
                    xform_op = xform.AddXformOp(UsdGeom.XformOp.TypeTransform, UsdGeom.XformOp.PrecisionDouble)
                xform_op.Set(mat)
            self._played_frame_count += 1

    def _cleanup_playback_resources(self):
        self._set_viewport_camera("/OmniverseKit_Persp")
        stage = omni.usd.get_context().get_stage()
        if stage:
            world = stage.GetPrimAtPath("/World")
            if world.IsValid():
                to_delete = [str(c.GetPath()) for c in world.GetChildren() if c.GetName().startswith("Recorded_Cam")]
                if to_delete:
                    omni.kit.commands.execute("DeletePrims", paths=to_delete)
        self._playback_camera_path = ""

    def _finalize_fps_record(self):
        duration = time.time() - self._playback_start_time
        if duration <= 0: return
        real_fps = self._played_frame_count / duration
        record_str = f"#{len(self._fps_history)+1}: {real_fps:.1f} FPS ({duration:.2f}s)"
        self._fps_history.append(record_str)
        if len(self._fps_history) > 5: self._fps_history.pop(0)
        
        if self._vstack_history:
            self._vstack_history.clear()
            with self._vstack_history:
                for rec in reversed(self._fps_history):
                    ui.Label(rec, height=14, style={"color": 0xFFDDDDDD, "font_size": 12})

    # --- [중요] Nucleus & Local File I/O Logic ---
    def _on_save_file(self):
        if not self._recorded_data:
            self._log_message("Save Failed: Empty.")
            return
        
        path = self._field_filepath.model.get_value_as_string()
        out = []
        for f in self._recorded_data:
            p, r = f["pos"], f["rot"]
            out.append({"p": (p[0],p[1],p[2]), "r": (r.GetReal(), r.GetImaginary()[0], r.GetImaginary()[1], r.GetImaginary()[2])})
        
        try:
            # Python 객체를 JSON String(bytes)으로 변환
            json_str = json.dumps(out, indent=4)
            
            # omni.client를 사용하여 쓰기 (Nucleus 지원)
            result = omni.client.write_file(path, json_str.encode("utf-8"))
            
            if result != omni.client.Result.OK:
                raise Exception(f"Omni Client Error: {result}")

            if self._lbl_status: self._lbl_status.text = "Saved"
            # 파일명만 깔끔하게 로그에 표시
            self._log_message(f"Saved: .../{path.split('/')[-1]}")
            
        except Exception as e: 
            self._log_message(f"Save Error: {e}")

    def _on_load_file(self):
        path = self._field_filepath.model.get_value_as_string()
        
        try:
            # omni.client를 사용하여 읽기 (Nucleus 지원)
            result, version, content = omni.client.read_file(path)
            
            if result != omni.client.Result.OK:
                self._log_message(f"Load Failed: {result}")
                return

            # memoryview -> bytes -> string -> json parse
            json_str = memoryview(content).tobytes().decode("utf-8")
            data = json.loads(json_str)
            
            self._recorded_data = []
            for d in data:
                p, r = d["p"], d["r"]
                self._recorded_data.append({"pos": Gf.Vec3d(*p), "rot": Gf.Quatd(r[0], Gf.Vec3d(r[1],r[2],r[3]))})
            
            if self._lbl_status: self._lbl_status.text = f"Loaded {len(data)}"
            if self._lbl_count: self._lbl_count.text = str(len(data))
            self._log_message(f"Loaded {len(data)} f.")
            
        except Exception as e:
            self._log_message(f"Load Error: {e}")

    def _copy_camera_attributes(self, src_prim, dst_prim):
        src = UsdGeom.Camera(src_prim)
        dst = UsdGeom.Camera(dst_prim)
        if not src or not dst: return
        attrs = [src.GetFocalLengthAttr(), src.GetHorizontalApertureAttr(), src.GetVerticalApertureAttr(),
                 src.GetClippingRangeAttr(), src.GetFStopAttr(), src.GetFocusDistanceAttr()]
        for a in attrs:
            if a.IsValid():
                da = dst_prim.GetAttribute(a.GetName())
                if da.IsValid(): da.Set(a.Get())

    def _set_viewport_camera(self, path):
        vp = vp_utility.get_active_viewport()
        if vp: 
            old_cam = self._current_cam_path
            old_name = old_cam.split("/")[-1] if "/" in old_cam else old_cam
            new_name = path.split("/")[-1] if "/" in path else path
            if old_name != new_name: self._log_message(f"View: {old_name}->{new_name}")
            vp.camera_path = path
            self._current_cam_path = path

    def on_menu_callback(self): pass
    def on_timeline_event(self, e): pass
    def on_physics_step(self, s): pass
    def on_stage_event(self, e): pass