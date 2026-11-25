// scp_look/look.ts
import { expo, frame, grain, hash, progress, spring, vignette } from "file:///F:/mockingbird/plugin/skills/motion-graphics/styles.js";
var PAPER = "#F2ECDF";
var INK = "#151412";
var RED = "#C0281D";
var MUTED = "#5F574A";
var TONE = { ink: INK, accent: RED, good: "#2E5B3A", bad: RED, muted: MUTED };
var MONO = '"Courier Prime", "Noto Color Emoji", monospace';
var COND = '"Oswald", "Noto Color Emoji", sans-serif';
function make(ctx, t, m) {
  const { W, H, u, X, Y } = frame(m);
  const g = globalThis;
  g.__scpB ??= new Map;
  const setFont = (size, family = MONO, weight = 700) => ctx.font = `${weight} ${Math.round(size * u)}px ${family}`;
  function strike(s, x, y, at, end, color) {
    if (t < at)
      return;
    const n = Math.min(s.length, Math.floor((t - at) / Math.max(0.05, end - at) * s.length) + 1);
    let cx = x;
    ctx.fillStyle = color;
    for (let i = 0;i < n; i++) {
      const ch = s[i];
      const born = at + (end - at) * i / s.length;
      const jolt = (1 - expo(progress(t, born, 0.12))) * 6 * u;
      ctx.globalAlpha = 0.82 + 0.18 * hash(i * 3.3 + x);
      ctx.fillText(ch, cx, y - jolt);
      cx += ctx.measureText(ch).width;
    }
    ctx.globalAlpha = 1;
  }
  return {
    surface() {
      const key = `${W}x${H}`;
      let desk = g.__scpB.get(key);
      if (!desk) {
        desk = new OffscreenCanvas(W, H);
        const c = desk.getContext("2d");
        c.fillStyle = "#C8A262";
        c.fillRect(0, 0, W, H);
        for (let i = 0;i < 1800; i++) {
          c.fillStyle = `rgba(110,74,28,${0.08 * hash(i)})`;
          c.fillRect(hash(i * 1.1) * W, hash(i * 2.3) * H, (2 + 6 * hash(i * 4)) * u, u);
        }
        c.save();
        c.translate(W / 2, H / 2);
        c.rotate(-0.012);
        c.shadowColor = "rgba(40,24,6,0.45)";
        c.shadowBlur = 30 * u;
        c.shadowOffsetY = 10 * u;
        c.fillStyle = PAPER;
        c.fillRect(-W * 0.45, -H * 0.455, W * 0.9, H * 0.91);
        c.restore();
        for (let i = 0;i < 1400; i++) {
          c.fillStyle = `rgba(90,70,40,${0.05 * hash(i * 9)})`;
          c.fillRect(W * 0.05 + hash(i * 3.7) * W * 0.9, H * 0.05 + hash(i * 5.1) * H * 0.9, 2 * u, 2 * u);
        }
        g.__scpB.set(key, desk);
      }
      ctx.save();
      const z = 1.06 + 0.035 * Math.sin(t * 0.37);
      ctx.translate(W / 2 + Math.sin(t * 0.29) * 0.02 * W, H / 2 + Math.sin(t * 0.41 + 1) * 0.012 * H);
      ctx.rotate(0.016 * Math.sin(t * 0.23 + 2));
      ctx.scale(z, z);
      ctx.translate(-W / 2, -H / 2);
      ctx.fillStyle = "#1F1610";
      ctx.fillRect(-W * 0.3, -H * 0.3, W * 1.6, H * 1.6);
      ctx.drawImage(desk, 0, 0);
    },
    title(s, o = {}) {
      const { x = 0.1, y = 0.11, size = 130, at = 0, dur = 0.7 } = o;
      setFont(size);
      ctx.textBaseline = "alphabetic";
      ctx.textAlign = "left";
      strike(s, X(x), Y(y), at, at + dur, INK);
      const w = ctx.measureText(s).width;
      const dashes = Math.floor(expo(progress(t, at + dur, 0.5)) * 12);
      ctx.fillStyle = INK;
      for (let i = 0;i < dashes; i++)
        ctx.fillRect(X(x) + i * w / 12, Y(y) + 22 * u, w / 12 - 8 * u, 7 * u);
    },
    label(s, x, y, o = {}) {
      const { at = 0, size = 36, tone = "ink" } = o;
      setFont(size);
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      strike(s.toUpperCase(), X(x), Y(y), at, at + s.length * 0.025, TONE[tone]);
    },
    node(x, y, r, o = {}) {
      const at = o.at ?? 0;
      ctx.fillStyle = "#1F1610";
      for (let k = 0;k < 2; k++) {
        if (t < at + k * 0.12)
          continue;
        ctx.beginPath();
        ctx.arc(X(x), Y(y), r * u, k * Math.PI, (k + 1) * Math.PI);
        ctx.fill();
      }
    },
    box(x, y, w, h, o = {}) {
      const at = o.at ?? 0;
      if (t < at)
        return;
      const [x0, y0, bw, bh] = [X(x), Y(y), X(w), Y(h)];
      const drop = 1 - spring(t, { start: at, stiffness: 220, damping: 15 });
      ctx.save();
      ctx.translate(x0 + bw / 2, y0 + bh / 2 - drop * 60 * u);
      ctx.rotate(0.03 + drop * 0.2);
      ctx.fillStyle = "#FBF8F1";
      ctx.fillRect(-bw / 2, -bh / 2, bw, bh);
      const img = ctx.createLinearGradient(-bw / 2, -bh / 2, bw / 2, bh / 2);
      img.addColorStop(0, "#56524C");
      img.addColorStop(1, "#1E1C19");
      ctx.fillStyle = img;
      ctx.fillRect(-bw / 2 + 14 * u, -bh / 2 + 14 * u, bw - 28 * u, bh - 42 * u);
      for (const [k, sx] of [[0, -1], [1, 1]]) {
        if (t < at + 0.35 + k * 0.2)
          continue;
        ctx.save();
        ctx.translate(sx * bw / 2, -bh / 2);
        ctx.rotate(sx * 0.6);
        ctx.fillStyle = "rgba(235,228,200,0.8)";
        ctx.fillRect(-55 * u, -18 * u, 110 * u, 36 * u);
        ctx.restore();
      }
      ctx.restore();
    },
    link(x1, y1, x2, y2, o = {}) {
      const { at = 0, dur = 0.5, tone = "accent", head = true } = o;
      const [ax, ay, bx, by] = [X(x1), Y(y1), X(x2), Y(y2)];
      const n = 10;
      const shown = Math.floor(expo(progress(t, at, dur)) * n);
      ctx.strokeStyle = TONE[tone];
      ctx.lineWidth = 6 * u;
      ctx.lineCap = "round";
      for (let i = 0;i < shown; i++) {
        ctx.beginPath();
        ctx.moveTo(ax + (bx - ax) * i / n, ay + (by - ay) * i / n);
        ctx.lineTo(ax + (bx - ax) * (i + 0.6) / n, ay + (by - ay) * (i + 0.6) / n);
        ctx.stroke();
      }
      if (head && shown === n) {
        const a = Math.atan2(by - ay, bx - ax);
        ctx.beginPath();
        ctx.moveTo(bx - Math.cos(a - 0.5) * 30 * u, by - Math.sin(a - 0.5) * 30 * u);
        ctx.lineTo(bx, by);
        ctx.lineTo(bx - Math.cos(a + 0.5) * 30 * u, by - Math.sin(a + 0.5) * 30 * u);
        ctx.stroke();
      }
    },
    store(x, y, w, h, o = {}) {
      const at = o.at ?? 0;
      const sides = Math.floor(expo(progress(t, at, 0.6)) * 4);
      const [x0, y0, bw, bh] = [X(x), Y(y), X(w), Y(h)];
      const pts = [[x0, y0], [x0 + bw, y0], [x0 + bw, y0 + bh], [x0, y0 + bh], [x0, y0]];
      ctx.strokeStyle = INK;
      ctx.lineWidth = 6 * u;
      for (let i = 0;i < sides; i++) {
        ctx.beginPath();
        ctx.moveTo(pts[i][0], pts[i][1]);
        ctx.lineTo(pts[i + 1][0], pts[i + 1][1]);
        ctx.stroke();
      }
    },
    stat(s, x, y, o = {}) {
      const { at = 0, dur = 1, size = 160, sub = "", count, tone = "accent" } = o;
      if (t < at)
        return;
      const n = count ? Math.round(count[0] + (count[1] - count[0]) * expo(progress(t, at, dur))) : null;
      const text = (n === null ? "" : `${n} `) + s.toUpperCase();
      setFont(size, COND, 700);
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      let cx = X(x);
      for (let i = 0;i < text.length; i++) {
        const born = at + i * 0.07;
        if (t < born)
          break;
        const drop = (1 - spring(t, { start: born, stiffness: 320, damping: 14 })) * 80 * u;
        ctx.fillStyle = TONE[tone];
        ctx.fillText(text[i], cx, Y(y) - drop);
        cx += ctx.measureText(text[i]).width;
      }
      if (sub) {
        setFont(34);
        ctx.textBaseline = "middle";
        strike(sub.toUpperCase(), X(x), Y(y) + 56 * u, at + 0.6, at + 0.6 + sub.length * 0.02, MUTED);
      }
    },
    mark(kind, x, y, o = {}) {
      const { at = 0, size = 70, tone = kind === "check" ? "good" : "bad" } = o;
      const r = size * u;
      const strokes = kind === "check" ? [[[-r, 0], [-r * 0.2, r * 0.7]], [[-r * 0.2, r * 0.7], [r, -r * 0.8]]] : [[[-r, -r], [r, r]], [[r, -r], [-r, r]]];
      ctx.save();
      ctx.translate(X(x), Y(y));
      ctx.strokeStyle = TONE[tone];
      ctx.lineWidth = 14 * u;
      ctx.lineCap = "round";
      strokes.forEach(([a, b], i) => {
        const p = expo(progress(t, at + i * 0.18, 0.18));
        if (p <= 0)
          return;
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p);
        ctx.stroke();
      });
      ctx.restore();
    },
    stamp(s, x, y, o = {}) {
      const { at = 0, size = 64, angle = -0.07, maxW = 0.84, out = Infinity } = o;
      if (t < at || t > out)
        return;
      setFont(size, COND, 700);
      const lines = [];
      for (const w of s.toUpperCase().split(" ")) {
        const last = lines[lines.length - 1];
        if (last && ctx.measureText(`${last} ${w}`).width < X(maxW) - 70 * u)
          lines[lines.length - 1] = `${last} ${w}`;
        else
          lines.push(w);
      }
      const lh = size * u * 1.12;
      const bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 70 * u;
      const bh = lines.length * lh + 44 * u;
      ctx.save();
      ctx.translate(X(x), Y(y));
      ctx.rotate(angle);
      ctx.strokeStyle = ctx.fillStyle = RED;
      ctx.lineWidth = 10 * u;
      const c = [[-bw / 2, -bh / 2], [bw / 2, -bh / 2], [bw / 2, bh / 2], [-bw / 2, bh / 2], [-bw / 2, -bh / 2]];
      for (let i = 0;i < 4; i++) {
        const p = expo(progress(t, at + i * 0.06, 0.08));
        if (p <= 0)
          break;
        ctx.beginPath();
        ctx.moveTo(c[i][0], c[i][1]);
        ctx.lineTo(c[i][0] + (c[i + 1][0] - c[i][0]) * p, c[i][1] + (c[i + 1][1] - c[i][1]) * p);
        ctx.stroke();
      }
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      let k = 0;
      lines.forEach((l, li) => {
        let cx = -ctx.measureText(l).width / 2;
        for (const ch of l) {
          const born = at + 0.28 + k++ * 0.025;
          if (t >= born) {
            const press = 1 + 0.5 * (1 - expo(progress(t, born, 0.1)));
            const cw = ctx.measureText(ch).width;
            ctx.save();
            ctx.translate(cx + cw / 2, -bh / 2 + 22 * u + lh * (li + 0.5));
            ctx.scale(press, press);
            ctx.fillText(ch, -cw / 2, 0);
            ctx.restore();
          }
          cx += ctx.measureText(ch).width;
        }
      });
      ctx.restore();
    },
    redact(x, y, w, o = {}) {
      const { at = 0, size = 40 } = o;
      ctx.fillStyle = "#111";
      for (let k = 0;k < 3; k++) {
        const p = expo(progress(t, at + k * 0.09, 0.22));
        if (p <= 0)
          continue;
        const off = (k - 1) * size * u * 0.32;
        ctx.beginPath();
        ctx.roundRect(X(x) - 4 * u, Y(y) + off - size * u * 0.28, (X(w) + 8 * u) * p, size * u * 0.56, size * u * 0.28);
        ctx.fill();
      }
    },
    line(s, x, y, o = {}) {
      const { at = 0, end = at + 2, size = 66, w = 0.8, out = Infinity, tone = "ink" } = o;
      if (t < at || t > out)
        return y;
      setFont(size);
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      const lines = [];
      for (const wd of s.split(/\s+/)) {
        const last = lines[lines.length - 1];
        if (last && ctx.measureText(`${last} ${wd}`).width < X(w))
          lines[lines.length - 1] = `${last} ${wd}`;
        else
          lines.push(wd);
      }
      const total = lines.reduce((n, l) => n + l.length + 1, 0);
      let c = 0;
      lines.forEach((l, i) => {
        const la = at + (end - at) * c / total;
        c += l.length + 1;
        strike(l, X(x), Y(y) + i * size * u * 1.28, la, at + (end - at) * c / total, TONE[tone]);
      });
      return y + lines.length * size * u * 1.28 / H;
    },
    finish() {
      ctx.restore();
      vignette(ctx, m, 0.4, "30,18,6");
      grain(ctx, m, t, 0.045);
    }
  };
}
var look_default = { id: "scp-on-the-desk", name: "On the desk", category: "scp", make };
export {
  look_default as default
};
