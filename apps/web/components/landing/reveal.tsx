"use client";

import gsap from "gsap";
import { useEffect, useRef, type ReactNode } from "react";

type RevealProps = {
  children: ReactNode;
  className?: string;
};

/**
 * Landing-page root. Owns all GSAP motion for its subtree (hero lines, hero
 * fades, `[data-reveal]`, `[data-bar]`, `[data-count]`) plus smooth scrolling
 * for same-page anchor links.
 */
export function Reveal({ children, className }: RevealProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return;
      }
      const link = (event.target as Element | null)?.closest<HTMLAnchorElement>(
        'a[href^="#"]',
      );
      const id = link?.getAttribute("href")?.slice(1);
      const target = id ? document.getElementById(id) : null;
      if (!target) return;
      event.preventDefault();
      const top =
        id === "top"
          ? 0
          : target.getBoundingClientRect().top +
            window.scrollY +
            (id === "how" ? window.innerHeight * 0.02 : -64);
      window.scrollTo({ top, behavior: reduceMotion ? "auto" : "smooth" });
      history.replaceState(null, "", `#${id}`);
    };
    root.addEventListener("click", onClick);

    if (reduceMotion) {
      return () => root.removeEventListener("click", onClick);
    }

    root.dataset.motion = "ready";
    let observer: IntersectionObserver | undefined;

    const ctx = gsap.context(() => {
      // `y: 0` is explicit because the pre-hydration CSS hides lines with a
      // transform that GSAP would otherwise parse into a leftover offset.
      gsap.fromTo(
        "[data-hero-line]",
        { yPercent: 110, y: 0 },
        {
          yPercent: 0,
          y: 0,
          duration: 1.2,
          ease: "expo.out",
          stagger: 0.09,
          delay: 0.1,
        },
      );
      gsap.fromTo(
        "[data-hero-fade]",
        { opacity: 0, y: 20 },
        {
          opacity: 1,
          y: 0,
          duration: 1,
          ease: "expo.out",
          stagger: 0.08,
          delay: 0.45,
        },
      );

      const elements = gsap.utils.toArray<HTMLElement>("[data-reveal]");
      gsap.set(elements, { opacity: 0, y: 56 });

      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            const el = entry.target as HTMLElement;
            observer?.unobserve(el);
            ctx.add(() => {
              gsap.to(el, { opacity: 1, y: 0, duration: 1, ease: "expo.out" });
              el.querySelectorAll<HTMLElement>("[data-bar]").forEach((bar) => {
                gsap.fromTo(
                  bar,
                  { scaleX: 0 },
                  { scaleX: 1, duration: 1.4, ease: "expo.out", delay: 0.2 },
                );
              });
              el.querySelectorAll<HTMLElement>("[data-count]").forEach((n) => {
                const end = Number(n.dataset.count) || 0;
                const counter = { v: 0 };
                n.textContent = "0";
                gsap.to(counter, {
                  v: end,
                  duration: 1.4,
                  ease: "power3.out",
                  delay: 0.15,
                  onUpdate: () => {
                    n.textContent = String(Math.round(counter.v));
                  },
                  onComplete: () => {
                    n.textContent = String(end);
                  },
                });
              });
            });
          }
        },
        { threshold: 0.2 },
      );
      elements.forEach((el) => observer?.observe(el));
    }, root);

    return () => {
      root.removeEventListener("click", onClick);
      observer?.disconnect();
      ctx.revert();
      // Restore final values in case a count-up was interrupted mid-tween.
      root.querySelectorAll<HTMLElement>("[data-count]").forEach((n) => {
        n.textContent = n.dataset.count ?? n.textContent;
      });
      delete root.dataset.motion;
    };
  }, []);

  return (
    <div ref={rootRef} className={className}>
      {children}
    </div>
  );
}
