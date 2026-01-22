import os
import time
import uuid
from datetime import datetime

import tkinter as tk
from tkinter import ttk

import moderngl_window as mglw
from PIL import Image

# from https://www.shadertoy.com/view/wtscDX

VERTEX_SHADER = """
#version 330
in vec2 in_position;
void main() { gl_Position = vec4(in_position, 0.0, 1.0); }
"""

FRAGMENT_SHADER = """
#version 330

uniform vec2  iResolution;
uniform vec2  u_center;
uniform float u_zoom;
uniform vec2  u_c;

out vec4 fragColor;

void mainImage(out vec4 fragColorOut, in vec2 fragCoord)
{
    vec2 v = (fragCoord.xy - iResolution.xy/2.0) / min(iResolution.y, iResolution.x);

    v *= u_zoom;
    v += u_center;

    vec2 m = vec2(0.42, 0.6);

    vec2 z = v;
    vec2 c = u_c;

    float iter = 1.0;
    vec3 sum = vec3(0.0);
    vec3 sum2;

    float M  = 200000.0;
    float M2 = M*M;

    #define N 60
    for (int i = 1; i < N; ++i)
    {
        iter = float(i);
        float angle = atan(z.y, z.x);
        sum2 = sum;
        sum += sin(angle * vec3(7, 9, 6)) * 0.5 + 0.5;

        if (dot(z, z) > M2) break;

        z = vec2(z.x*z.x - z.y*z.y, z.x*z.y + z.y*z.x) + c;
    }

    sum  /= iter;
    sum2 /= (iter - 1.0);

    float f = -log2(log(length(z))/log(M2));
    sum = mix(sum2, sum, clamp(f, 0.0, 1.0));

    vec3 color = sum * vec3(1.0, 0.9, 0.82);
    color = (color - m.x) * (m.y * 10.0 + 1.0);

    if (dot(z, z) < M) color = vec3(0.0);

    fragColorOut = vec4(color, 1.0);
}

void main() {
    mainImage(fragColor, gl_FragCoord.xy);
}
"""


class JuliaWindow(mglw.WindowConfig):
    gl_version = (3, 3)
    title = "Julia (GLSL) — Tk sliders + Save PNG"
    window_size = (1100, 800)
    resizable = True
    aspect_ratio = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Fullscreen quad
        import struct
        verts = [
            -1.0, -1.0,
             1.0, -1.0,
            -1.0,  1.0,
            -1.0,  1.0,
             1.0, -1.0,
             1.0,  1.0,
        ]
        self.vbo = self.ctx.buffer(struct.pack(f"{len(verts)}f", *verts))

        self.prog = self.ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER,
        )
        self.vao = self.ctx.vertex_array(self.prog, [(self.vbo, "2f", "in_position")])

        # Julia params
        self.c_real = 0.4
        self.c_imag = -0.325
        self.center = [0.0, 0.0]
        self.zoom = 2.5
        self._mouse_pos = None
        self._left_down = False

        # output directory
        self.out_dir = "renders"
        os.makedirs(self.out_dir, exist_ok=True)

        # --- Tk UI in a separate window ---
        self._save_requested = False
        self._tk = tk.Tk()
        self._tk.title("Julia controls")

        self._real_var = tk.DoubleVar(value=self.c_real)
        self._imag_var = tk.DoubleVar(value=self.c_imag)

        ttk.Label(self._tk, text="c.real").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Scale(
            self._tk, from_=-2.0, to=2.0, variable=self._real_var,
            orient="horizontal", length=260
        ).grid(row=0, column=1, padx=8, pady=6)

        ttk.Label(self._tk, text="c.imag").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Scale(
            self._tk, from_=-2.0, to=2.0, variable=self._imag_var,
            orient="horizontal", length=260
        ).grid(row=1, column=1, padx=8, pady=6)

        self._readout = ttk.Label(self._tk, text=self._format_c())
        self._readout.grid(row=2, column=0, columnspan=2, padx=8, pady=6)

        ttk.Button(self._tk, text="Save PNG (unique)", command=self._request_save)\
            .grid(row=3, column=0, columnspan=2, padx=8, pady=10, sticky="ew")

        self._tk.protocol("WM_DELETE_WINDOW", self._on_tk_close)
        self._tk_open = True

    def _format_c(self):
        return (
            f"c = {self._real_var.get():+.6f} {self._imag_var.get():+.6f}i   "
            f"(renders -> {os.path.abspath(self.out_dir)})"
        )

    def _request_save(self):
        self._save_requested = True

    def _on_tk_close(self):
        # hide controls; keep OpenGL window alive
        self._tk_open = False
        self._tk.withdraw()

    def _unique_filename(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = uuid.uuid4().hex[:10]
        return os.path.join(self.out_dir, f"julia_{stamp}_{token}.png")

    def _screen_to_world(self, x, y):
        w, h = self.wnd.buffer_size
        scale = float(min(w, h))
        if scale == 0.0:
            return self.center[0], self.center[1]
        return (
            (x - w * 0.5) / scale * self.zoom + self.center[0],
            (y - h * 0.5) / scale * self.zoom + self.center[1],
        )

    def _save_png(self):
        w, h = self.wnd.buffer_size
        raw = self.ctx.screen.read(components=3, alignment=1)
        img = Image.frombytes("RGB", (w, h), raw).transpose(Image.FLIP_TOP_BOTTOM)
        path = self._unique_filename()
        img.save(path)
        print(f"[saved] {path}")

    def on_mouse_position_event(self, x, y, dx, dy):
        self._mouse_pos = (x, y)

    def on_mouse_press_event(self, x, y, button):
        if button == 1:
            self._left_down = True
            self._mouse_pos = (x, y)
            self.center[0], self.center[1] = self._screen_to_world(x, y)

    def on_mouse_release_event(self, x, y, button):
        if button == 1:
            self._left_down = False

    def on_mouse_drag_event(self, x, y, dx, dy):
        self._mouse_pos = (x, y)
        if not self._left_down:
            return
        w, h = self.wnd.buffer_size
        scale = float(min(w, h))
        if scale == 0.0:
            return
        self.center[0] -= dx / scale * self.zoom
        self.center[1] += dy / scale * self.zoom

    def on_mouse_scroll_event(self, x_offset, y_offset):
        if y_offset == 0.0:
            return
        w, h = self.wnd.buffer_size
        if w == 0 or h == 0:
            return
        if self._mouse_pos is None:
            mx, my = w * 0.5, h * 0.5
        else:
            mx, my = self._mouse_pos

        before_x, before_y = self._screen_to_world(mx, my)
        zoom_factor = 0.9 ** y_offset
        self.zoom = max(1e-6, min(1e6, self.zoom * zoom_factor))
        after_x, after_y = self._screen_to_world(mx, my)
        self.center[0] += before_x - after_x
        self.center[1] += before_y - after_y

    # ---- moderngl-window expects THIS name in your installed version ----
    def on_render(self, time_now: float, frame_time: float):
        # Pump Tk without blocking
        if self._tk_open:
            self._tk.update_idletasks()
            self._tk.update()

            self.c_real = float(self._real_var.get())
            self.c_imag = float(self._imag_var.get())
            self._readout.configure(text=self._format_c())

        # Draw fractal
        w, h = self.wnd.buffer_size
        self.prog["iResolution"].value = (float(w), float(h))
        self.prog["u_center"].value = (self.center[0], self.center[1])
        self.prog["u_zoom"].value = float(self.zoom)
        self.prog["u_c"].value = (self.c_real, self.c_imag)

        self.vao.render()

        if self._save_requested:
            self._save_requested = False
            self._save_png()

    # Optional compatibility shim: if some future version calls render()
    def render(self, time_delta: float):
        self.on_render(time.time(), time_delta)


if __name__ == "__main__":
    mglw.run_window_config(JuliaWindow)
