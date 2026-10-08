import { html } from "../lib.js";

const I = (d) => html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" dangerouslySetInnerHTML=${{ __html: d }}></svg>`;

export const Icon = {
  prev: () => I('<path d="M15 6l-6 6 6 6"/>'),
  next: () => I('<path d="M9 6l6 6-6 6"/>'),
  stepBack: () => I('<path d="M11 6l-6 6 6 6M19 6l-6 6 6 6"/>'),
  stepFwd: () => I('<path d="M13 6l6 6-6 6M5 6l6 6-6 6"/>'),
  now: () => I('<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>'),
  pin: () => I('<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>'),
  moonIcon: () => I('<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>'),
  sun: () => I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
  eye: () => I('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  gear: () => I('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>'),
  help: () => I('<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01"/>'),
  plus: () => I('<path d="M12 5v14M5 12h14"/>'),
  x: () => I('<path d="M6 6l12 12M18 6L6 18"/>'),
  trash: () => I('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  link: () => I('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
  search: () => I('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  download: () => I('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>'),
  upload: () => I('<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>'),
};

/** The artairmass mark: a crescent over an airmass arc. */
export const Logo = () => html`<svg viewBox="0 0 64 64" aria-hidden="true">
  <path d="M40 10a21 21 0 1 0 13 36 18 18 0 1 1-13-36z" fill="var(--moon)" opacity="0.92"/>
  <path d="M7 52 C 22 22, 42 22, 57 52" fill="none" stroke="var(--accent)" stroke-width="4.5" stroke-linecap="round"/>
</svg>`;
