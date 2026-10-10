(() => {
    const menu = document.getElementById('workspace-menu');
    const sidebar = document.getElementById('workspace-sidebar');
    const overlay = document.getElementById('workspace-overlay');
    if (!menu || !sidebar || !overlay) return;
    sidebar.querySelectorAll('.is-active').forEach(link => link.setAttribute('aria-current', 'page'));
    const mobile = matchMedia('(max-width: 1000px)');
    function setOpen(open, restoreFocus = false) {
        open = open && mobile.matches;
        document.body.classList.toggle('ops-nav-open', open);
        menu.setAttribute('aria-expanded', String(open));
        menu.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
        overlay.hidden = !open;
        sidebar.inert = mobile.matches && !open;
        if (open) sidebar.querySelector('a')?.focus();
        else if (restoreFocus) menu.focus();
    }
    menu.addEventListener('click', () => setOpen(!document.body.classList.contains('ops-nav-open')));
    overlay.addEventListener('click', () => setOpen(false, true));
    document.addEventListener('keydown', event => {
        if (!document.body.classList.contains('ops-nav-open')) return;
        if (event.key === 'Escape') { setOpen(false, true); return; }
        if (event.key === 'Tab') {
            const links = [...sidebar.querySelectorAll('a')];
            if (!links.length) return;
            if (event.shiftKey && document.activeElement === links[0]) { event.preventDefault(); links.at(-1).focus(); }
            else if (!event.shiftKey && document.activeElement === links.at(-1)) { event.preventDefault(); links[0].focus(); }
        }
    });
    mobile.addEventListener('change', () => setOpen(false));
    setOpen(false);
})();
