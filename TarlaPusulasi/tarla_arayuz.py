"""Ortak kaydırma, pencere ve okunabilirlik yardımcıları."""
import tkinter as tk


class ToolTab(tk.Frame):
    """Araç içeriği ve sekme kapatılırken çalışacak işlem."""

    def __init__(self, parent, activate, **kwargs):
        super().__init__(parent, **kwargs)
        self._activate = activate
        self._jobs = set()
        self.on_close = self.destroy

    def lift(self):
        self._activate(self)

    def request_close(self):
        self.on_close()

    def after(self, delay, callback=None, *args):
        if callback is None:
            return super().after(delay)

        def run():
            self._jobs.discard(job)
            callback(*args)

        job = super().after(delay, run)
        self._jobs.add(job)
        return job

    def after_cancel(self, job):
        super().after_cancel(job)
        self._jobs.discard(job)

    def destroy(self):
        for job in tuple(self._jobs):
            self.after_cancel(job)
        super().destroy()


class WheelRouter:
    """En içteki kaydırılabilir alanı kaydırır; sınırda üst alana geçer."""
    TAG = "TarlaWheel"
    def __init__(self, root):
        self.root = root
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_class(self.TAG, seq, self.wheel)
        self.scan()

    def scan(self):
        def visit(w):
            tags = w.bindtags()
            if self.TAG not in tags:
                w.bindtags((self.TAG,) + tags)
            for child in w.winfo_children():
                visit(child)
        if self.root.winfo_exists():
            visit(self.root)
            self.root.after(250, self.scan)

    def wheel(self, event):
        num = getattr(event, "num", None)
        if num in (4, 5):
            steps = -2 if num == 4 else 2
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            steps = -max(1, abs(int(delta / 120))) if delta > 0 else max(1, abs(int(delta / 120)))
        axis = "x" if event.state & 1 else "y"
        w = event.widget
        while w is not None:
            try:
                if getattr(w, '_wheel_boundary', False):
                    return 'break'
                if isinstance(w, (tk.Canvas, tk.Text, tk.Listbox)):
                    view = getattr(w, axis + "view")
                    first, last = view()
                    can_move = (steps < 0 and first > .0001) or (steps > 0 and last < .9999)
                    if can_move:
                        getattr(w, axis + "view_scroll")(steps, "units")
                        return "break"
                w = w.master
            except (tk.TclError, AttributeError, ValueError):
                w = getattr(w, "master", None)
        return None


def fold(parent, title, bg, fg, font):
    host = tk.Frame(parent, bg=bg)
    host.pack(fill="x", pady=(10, 4))
    content = tk.Frame(host, bg=bg)
    expanded = [False]
    def toggle():
        expanded[0] = not expanded[0]
        btn.configure(text=("− " if expanded[0] else "+ ") + title)
        if expanded[0]:
            content.pack(fill="x", padx=4, pady=8)
        else:
            content.pack_forget()
    btn = tk.Button(host, text="+ " + title, command=toggle, bg=bg, fg=fg,
                    activebackground=bg, activeforeground=fg, relief="flat",
                    anchor="w", font=font, padx=14, pady=10, cursor="hand2")
    btn.pack(fill="x")
    return content
