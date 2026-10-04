"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useWorkspaceNavigation(enabled: boolean, role: string, sections: readonly string[], initialSection: string) {
  const [active, setActive] = useState(initialSection);
  const offset = useRef(100);
  const destination = useRef<string | null>(null);

  const scrollToSection = useCallback((id: string, smooth: boolean, focus: boolean) => {
    const section = document.getElementById(`${role}-${id}`);
    if (!section) return;
    destination.current = id;
    setActive(section.closest("[data-workspace-section]")?.getAttribute("data-workspace-section") || id);
    if (focus) document.getElementById(`${role}-${id}-title`)?.focus({ preventScroll: true });
    const top = Math.max(0, window.scrollY + section.getBoundingClientRect().top - offset.current);
    window.scrollTo({ top, behavior: smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "instant" });
  }, [role]);

  const navigate = useCallback((id: string) => {
    if (!enabled || !sections.includes(id)) return;
    const href = role === "admin" ? `/admin/${id}` : `#${role}-${id}`;
    const current = role === "admin" ? window.location.pathname + window.location.hash : window.location.hash;
    if (current !== href) window.history.pushState(null, "", href);
    scrollToSection(id, true, true);
  }, [enabled, role, sections, scrollToSection]);

  useEffect(() => {
    if (!enabled) return;
    const shell = document.querySelector<HTMLElement>(".workspace-shell");
    const sidebar = shell?.querySelector<HTMLElement>(".sidebar");
    const topbar = shell?.querySelector<HTMLElement>(".topbar");
    const elements = sections.map(id => document.getElementById(`${role}-${id}`)).filter((element): element is HTMLElement => !!element);
    if (!shell || !elements.length) return;
    let frame = 0;
    const previousScrollRestoration = window.history.scrollRestoration;
    if (role === "admin") window.history.scrollRestoration = "manual";

    function nestedAdminAnchor() {
      if (role !== "admin" || !window.location.hash.startsWith("#admin-")) return null;
      const anchor = document.getElementById(window.location.hash.slice(1));
      return anchor && !anchor.hasAttribute("data-workspace-section") ? anchor : null;
    }

    function syncAdminURL(id: string) {
      if (role !== "admin") return;
      // Keep in-section links (such as credential evidence) usable as anchors.
      const anchorSection = nestedAdminAnchor()?.closest("[data-workspace-section]")?.getAttribute("data-workspace-section");
      const href = `/admin/${anchorSection || id}${anchorSection ? window.location.hash : ""}`;
      if (window.location.pathname + window.location.hash !== href) window.history.replaceState(null, "", href);
    }

    function updateOffset() {
      const mobileNav = window.matchMedia("(max-width: 640px)").matches ? sidebar?.getBoundingClientRect().height || 0 : 0;
      offset.current = mobileNav + (topbar?.getBoundingClientRect().height || 0) + 20;
      shell!.style.setProperty("--workspace-nav-height", `${mobileNav}px`);
      shell!.style.setProperty("--workspace-scroll-offset", `${offset.current}px`);
    }

    function updateActive() {
      frame = 0;
      // A sidebar jump can cross several sections. Keep its URL and highlight
      // stable until the user resumes scrolling or interacting with the page.
      if (role === "admin" && destination.current) return;
      const line = offset.current + 8;
      let current = sections[0];
      for (const element of elements) {
        if (element.getBoundingClientRect().top <= line) current = element.id.slice(role.length + 1);
      }
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 3) current = sections[sections.length - 1];
      setActive(current);
      syncAdminURL(current);
    }

    function scheduleActive() {
      if (!frame) frame = requestAnimationFrame(updateActive);
    }

    function releaseDestination() {
      destination.current = null;
      // User interaction ends an anchor jump. A queued scroll frame must not
      // remove a newly clicked fragment before the browser reaches its target.
      if (nestedAdminAnchor()) window.history.replaceState(null, "", window.location.pathname);
      scheduleActive();
    }

    function restoreLocation() {
      const prefix = `#${role}-`;
      const id = window.location.hash.startsWith(prefix) ? window.location.hash.slice(prefix.length) : "";
      if (sections.includes(id)) {
        updateOffset();
        syncAdminURL(id);
        scrollToSection(id, false, false);
      } else if (nestedAdminAnchor()) {
        updateOffset();
        syncAdminURL(id);
        scrollToSection(id, false, false);
      } else if (role === "admin" && (!window.location.hash || id === "analytics")) {
        const pathSection = window.location.pathname.split("/")[2];
        const target = sections.includes(pathSection) ? pathSection : sections[0];
        updateOffset();
        syncAdminURL(target);
        scrollToSection(target, false, false);
      } else if (!window.location.hash) {
        scrollToSection(initialSection, false, false);
      } else {
        releaseDestination();
      }
    }

    const observer = new ResizeObserver(() => {
      updateOffset();
      // Keep an explicit jump aligned while preceding sections finish loading.
      // User input releases this so editing/expanding content never pulls them back.
      if (destination.current) scrollToSection(destination.current, false, false);
      else scheduleActive();
    });
    elements.forEach(element => observer.observe(element));
    if (sidebar) observer.observe(sidebar);
    if (topbar) observer.observe(topbar);
    updateOffset();
    if (role === "admin" || window.location.hash) restoreLocation();
    else if (initialSection !== sections[0]) scrollToSection(initialSection, false, false);
    else scheduleActive();
    window.addEventListener("scroll", scheduleActive, { passive: true });
    window.addEventListener("resize", scheduleActive);
    window.addEventListener("wheel", releaseDestination, { passive: true });
    window.addEventListener("touchstart", releaseDestination, { passive: true });
    window.addEventListener("pointerdown", releaseDestination, { passive: true });
    window.addEventListener("keydown", releaseDestination);
    window.addEventListener("hashchange", restoreLocation);
    window.addEventListener("popstate", restoreLocation);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      destination.current = null;
      if (role === "admin") window.history.scrollRestoration = previousScrollRestoration;
      window.removeEventListener("scroll", scheduleActive);
      window.removeEventListener("resize", scheduleActive);
      window.removeEventListener("wheel", releaseDestination);
      window.removeEventListener("touchstart", releaseDestination);
      window.removeEventListener("pointerdown", releaseDestination);
      window.removeEventListener("keydown", releaseDestination);
      window.removeEventListener("hashchange", restoreLocation);
      window.removeEventListener("popstate", restoreLocation);
    };
  }, [enabled, role, sections, initialSection, scrollToSection]);

  useEffect(() => {
    if (!enabled) return;
    const nav = document.querySelector<HTMLElement>(".workspace-shell .nav-items");
    const href = role === "admin" ? `/admin/${active}` : `#${role}-${active}`;
    const link = nav?.querySelector<HTMLElement>(`a[href="${href}"]`);
    if (!nav || !link) return;
    const navRect = nav.getBoundingClientRect(), linkRect = link.getBoundingClientRect();
    if (nav.scrollWidth > nav.clientWidth && (linkRect.left < navRect.left || linkRect.right > navRect.right)) {
      nav.scrollTo({ left: nav.scrollLeft + linkRect.left - navRect.left - (nav.clientWidth - linkRect.width) / 2, behavior: "instant" });
    }
    const sidebar = nav.closest<HTMLElement>(".sidebar");
    if (sidebar && sidebar.scrollHeight > sidebar.clientHeight) {
      const bounds = sidebar.getBoundingClientRect();
      if (linkRect.top < bounds.top + 12) sidebar.scrollBy({ top: linkRect.top - bounds.top - 12, behavior: "instant" });
      else if (linkRect.bottom > bounds.bottom - 12) sidebar.scrollBy({ top: linkRect.bottom - bounds.bottom + 12, behavior: "instant" });
    }
  }, [active, enabled, role]);

  return { active, navigate };
}
