/**
 * Attribution footer for the public deploy. Makes the fan-tribute nature of
 * the project explicit; credits De School's archive + Mixcloud as the source
 * of the audio; notes the non-commercial, derived-features-only stance.
 */
export function Colophon() {
  return (
    <footer className="colophon">
      <div className="colophon-stamp">colophon</div>
      <div className="colophon-body">
        A fan tribute — an unaffiliated browser over{" "}
        <a
          href="https://hetarchief.deschoolamsterdam.nl/"
          target="_blank"
          rel="noreferrer noopener"
        >
          hetarchief.deschoolamsterdam.nl
        </a>
        . Audio streams directly from Mixcloud; only derived numerical
        features (tempo, brightness, energy, mood labels) are stored. No
        commercial use. Built for listening while working.
      </div>
      <div className="colophon-meta">
        <a
          href="https://github.com/PLNech/le_archive"
          target="_blank"
          rel="noreferrer noopener"
        >
          source · github
        </a>
      </div>
    </footer>
  );
}
