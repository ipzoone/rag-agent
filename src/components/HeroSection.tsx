import "./HeroSection.css";

export default function HeroSection() {
  return (
    <>
      <div className="hero-topbar">
        <a href="#" className="active">Untuk Individu</a>
        <a href="#">Untuk Bisnis</a>
        <a href="#">Untuk Sekolah</a>
      </div>

      <div className="hero-navbar">
        <div className="hero-logo">
          <div className="hero-logo-mark">
            <span />
            <span />
          </div>
          <div className="hero-logo-text">CODE<span>POLITAN</span></div>
        </div>
        <div className="hero-menu">
          <div />
          <div />
          <div />
        </div>
      </div>

      <section className="hero-section">
        <div className="hero-copy">
          <span className="hero-badge">EKOSISTEM BELAJAR DEVELOPER SEJAK 2016</span>
          <h1>
            Jangan Bersaing dengan AI.
            <span className="hero-accent"> Jadilah Developer yang Menguasainya</span>
          </h1>
          <p className="hero-lead">
            Tempat belajar coding, AI, dan cybersecurity supaya kamu tetap relevan
            di era AI. Dibimbing mentor praktisi aktif, bareng komunitas 223.000+ member.
          </p>
          <div className="hero-cta-row">
            <a href="#" className="hero-btn hero-btn--primary">Mulai Sekarang Gratis</a>
            <a href="#" className="hero-btn hero-btn--outline">Lihat Semua Kelas</a>
          </div>
          <div className="hero-chip-row">
            <div className="hero-chip">Vibe Coding dengan AI</div>
            <div className="hero-chip">Ethical Hacking</div>
            <div className="hero-chip">Fullstack &amp; Fundamental</div>
          </div>
        </div>

        <div className="hero-visual">
          <span className="hero-cross c1">&#10011;</span>
          <span className="hero-cross c2">&#10011;</span>
          <span className="hero-cross c3">&#10011;</span>
          <span className="hero-cross c4">&#10011;</span>

          <div className="hero-visual-panel">
            <div className="hero-visual-placeholder">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
