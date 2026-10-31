/* ============================================================
   SHOPVERSE TEMPLATE - ALL Animations & Interactions
   Comprehensive animation suite for Northstar Store
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // =========================================================
    // 1. SCROLL PROGRESS BAR
    // =========================================================
    const progressBar = document.createElement('div');
    progressBar.className = 'sv-scroll-progress';
    document.body.prepend(progressBar);

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrollPercent = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
        progressBar.style.width = scrollPercent + '%';
    }, { passive: true });

    // =========================================================
    // 2. PRELOADER
    // =========================================================
    const preloader = document.getElementById('sv-preloader');
    if (preloader) {
        const hidePreloader = () => {
            preloader.classList.add('sv-hidden');
            document.body.style.overflow = 'auto';
            setTimeout(() => {
                initAOSAnimations();
                animateCounters();
                initSectionTitleAnimations();
            }, 200);
        };

        window.addEventListener('load', () => setTimeout(hidePreloader, 1500));
        setTimeout(() => { if (!preloader.classList.contains('sv-hidden')) hidePreloader(); }, 4000);
    } else {
        initAOSAnimations();
        animateCounters();
        initSectionTitleAnimations();
    }

    // =========================================================
    // 3. SCROLL TO TOP
    // =========================================================
    const scrollTopBtn = document.getElementById('sv-scroll-top');
    if (scrollTopBtn) {
        window.addEventListener('scroll', () => {
            scrollTopBtn.classList.toggle('sv-visible', window.pageYOffset > 500);
        }, { passive: true });

        scrollTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // =========================================================
    // 4. COUNTER ANIMATION (with easing)
    // =========================================================
    function animateCounters() {
        if (reduceMotion) return;
        const counters = document.querySelectorAll('.sv-stat-number[data-count]');

        const counterObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const counter = entry.target;
                    const target = parseInt(counter.getAttribute('data-count'));
                    const duration = 2000;
                    const startTime = performance.now();

                    const easeOutQuart = t => 1 - Math.pow(1 - t, 4);

                    const update = (currentTime) => {
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / duration, 1);
                        const easedProgress = easeOutQuart(progress);
                        const current = Math.ceil(easedProgress * target);
                        counter.textContent = current;
                        if (progress < 1) requestAnimationFrame(update);
                        else counter.textContent = target;
                    };
                    requestAnimationFrame(update);
                    counterObserver.unobserve(counter);
                }
            });
        }, { threshold: 0.5 });

        counters.forEach(c => counterObserver.observe(c));
    }

    // =========================================================
    // 5. AOS (Animate on Scroll) - Enhanced
    // =========================================================
    function initAOSAnimations() {
        const aosEls = document.querySelectorAll('[data-sv-aos]');
        if (reduceMotion) {
            aosEls.forEach(el => el.classList.add('sv-aos-animate'));
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const delay = parseInt(entry.target.getAttribute('data-sv-aos-delay') || 0);
                    setTimeout(() => entry.target.classList.add('sv-aos-animate'), delay);
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

        aosEls.forEach(el => observer.observe(el));
    }

    // =========================================================
    // 6. SECTION TITLE ANIMATED UNDERLINE
    // =========================================================
    function initSectionTitleAnimations() {
        const titles = document.querySelectorAll('.sv-section-title');
        if (reduceMotion) {
            titles.forEach(t => t.classList.add('sv-title-visible'));
            return;
        }

        const titleObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('sv-title-visible');
                    titleObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        titles.forEach(t => titleObserver.observe(t));
    }

    // =========================================================
    // 7. COUNTDOWN TIMERS (driven by genuine offer deadlines)
    // =========================================================
    function parseDeadlineMs(raw) {
        if (!raw || typeof raw !== 'string') return NaN;
        const parsed = Date.parse(raw.trim());
        return Number.isFinite(parsed) ? parsed : NaN;
    }

    function startCountdown() {
        const timerEl = document.querySelector('.sv-countdown-timer');
        if (!timerEl) return;

        const deadlineMs = parseDeadlineMs(timerEl.getAttribute('data-countdown-deadline'));
        if (Number.isNaN(deadlineMs)) {
            timerEl.hidden = true;
            return;
        }

        const labelEl = timerEl.querySelector('.sv-countdown-label');
        const boxesEl = timerEl.querySelector('.sv-countdown-boxes');
        const hoursEl = document.getElementById('sv-countdown-hours');
        const minutesEl = document.getElementById('sv-countdown-minutes');
        const secondsEl = document.getElementById('sv-countdown-seconds');
        if (!hoursEl || !minutesEl || !secondsEl) return;

        const tickEl = (el) => {
            const box = el.closest('.sv-countdown-box');
            if (box && !reduceMotion) {
                box.classList.remove('sv-tick');
                void box.offsetWidth;
                box.classList.add('sv-tick');
            }
        };

        let intervalId = null;
        const render = () => {
            const remainingSeconds = Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000));
            const totalHours = Math.floor(remainingSeconds / 3600);
            const minutes = Math.floor((remainingSeconds % 3600) / 60);
            const seconds = remainingSeconds % 60;

            const nextHours = String(totalHours).padStart(2, '0');
            const nextMinutes = String(minutes).padStart(2, '0');
            const nextSeconds = String(seconds).padStart(2, '0');

            if (hoursEl.textContent !== nextHours) tickEl(hoursEl);
            if (minutesEl.textContent !== nextMinutes) tickEl(minutesEl);
            if (secondsEl.textContent !== nextSeconds) tickEl(secondsEl);

            hoursEl.textContent = nextHours;
            minutesEl.textContent = nextMinutes;
            secondsEl.textContent = nextSeconds;

            if (remainingSeconds <= 0) {
                timerEl.classList.add('sv-timer-ended');
                timerEl.setAttribute('data-countdown-state', 'expired');
                if (labelEl) labelEl.textContent = 'Offer ended';
                if (boxesEl) boxesEl.hidden = true;
                if (intervalId !== null) clearInterval(intervalId);
                return false;
            }
            timerEl.classList.remove('sv-timer-ended');
            timerEl.setAttribute('data-countdown-state', 'active');
            if (labelEl) labelEl.textContent = 'Ends in:';
            if (boxesEl) boxesEl.hidden = false;
            return true;
        };

        if (render()) {
            intervalId = setInterval(render, 1000);
        }
    }
    startCountdown();

    // =========================================================
    // 8. OFFER TIMER (driven by genuine offer deadlines)
    // =========================================================
    function startOfferTimer() {
        const timerEl = document.querySelector('.sv-offer-timer');
        if (!timerEl) return;

        const deadlineMs = parseDeadlineMs(timerEl.getAttribute('data-offer-deadline'));
        if (Number.isNaN(deadlineMs)) {
            timerEl.hidden = true;
            return;
        }

        const statusEl = timerEl.querySelector('.sv-offer-status');
        const boxesEl = timerEl.querySelector('.sv-offer-timer-boxes');
        const daysEl = document.querySelector('.sv-offer-days');
        const hrsEl = document.querySelector('.sv-offer-hrs');
        const minsEl = document.querySelector('.sv-offer-mins');
        const secsEl = document.querySelector('.sv-offer-secs');
        if (!daysEl || !hrsEl || !minsEl || !secsEl) return;

        let intervalId = null;
        const render = () => {
            const remainingSeconds = Math.max(0, Math.floor((deadlineMs - Date.now()) / 1000));
            const days = Math.floor(remainingSeconds / 86400);
            const hrs = Math.floor((remainingSeconds % 86400) / 3600);
            const mins = Math.floor((remainingSeconds % 3600) / 60);
            const secs = remainingSeconds % 60;

            daysEl.textContent = String(days).padStart(2, '0');
            hrsEl.textContent = String(hrs).padStart(2, '0');
            minsEl.textContent = String(mins).padStart(2, '0');
            secsEl.textContent = String(secs).padStart(2, '0');

            if (remainingSeconds <= 0) {
                timerEl.classList.add('sv-timer-ended');
                timerEl.setAttribute('data-countdown-state', 'expired');
                if (statusEl) {
                    statusEl.textContent = 'Offer ended';
                    statusEl.hidden = false;
                }
                if (boxesEl) boxesEl.hidden = true;
                if (intervalId !== null) clearInterval(intervalId);
                return false;
            }
            timerEl.classList.remove('sv-timer-ended');
            timerEl.setAttribute('data-countdown-state', 'active');
            if (statusEl) statusEl.hidden = true;
            if (boxesEl) boxesEl.hidden = false;
            return true;
        };

        if (render()) {
            intervalId = setInterval(render, 1000);
        }
    }
    startOfferTimer();

    // =========================================================
    // 9. TOAST NOTIFICATIONS
    // =========================================================
    window.svShowToast = function(title, message, type) {
        type = type || 'success';
        const container = document.getElementById('sv-toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.classList.add('sv-toast');

        const iconMap = { success: 'fas fa-check-circle', error: 'fas fa-exclamation-circle', info: 'fas fa-info-circle' };
        const colorMap = { success: '#2ED573', error: '#FF6B6B', info: '#6C63FF' };

        toast.style.borderLeftColor = colorMap[type];
        toast.innerHTML = `
            <span class="sv-toast-icon" style="color: ${colorMap[type]}"><i class="${iconMap[type]}"></i></span>
            <div class="sv-toast-message"><strong>${title}</strong><span>${message}</span></div>
            <button class="sv-toast-close" onclick="this.parentElement.classList.add('sv-removing'); setTimeout(() => this.parentElement.remove(), 300)"><i class="fas fa-times"></i></button>
        `;
        container.appendChild(toast);

        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('sv-removing');
                setTimeout(() => toast.remove(), 300);
            }
        }, 3500);
    };

    // =========================================================
    // 10. PROGRESS BAR ANIMATION
    // =========================================================
    const progressObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const fills = entry.target.querySelectorAll('.sv-progress-fill');
                fills.forEach(fill => {
                    const width = fill.style.width;
                    if (reduceMotion) return;
                    fill.style.width = '0';
                    setTimeout(() => { fill.style.width = width; }, 400);
                });
            }
        });
    }, { threshold: 0.3 });

    document.querySelectorAll('.sv-flash-deals, .sv-deal-progress').forEach(s => progressObserver.observe(s));

    // =========================================================
    // 11. TILT EFFECT ON CATEGORY CARDS (3D perspective)
    // =========================================================
    if (!reduceMotion) {
        document.querySelectorAll('[data-sv-tilt]').forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                const centerX = rect.width / 2;
                const centerY = rect.height / 2;
                const rotateX = (y - centerY) / 12;
                const rotateY = (centerX - x) / 12;
                card.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-10px) scale(1.02)`;
            });

            card.addEventListener('mouseleave', () => {
                card.style.transform = 'perspective(800px) rotateX(0) rotateY(0) translateY(0) scale(1)';
            });
        });
    }

    // =========================================================
    // 12. HERO PARALLAX SHAPES + RINGS + PARTICLES
    // =========================================================
    const hero = document.querySelector('.sv-hero');
    if (hero && !reduceMotion) {
        // Mouse parallax on shapes
        window.addEventListener('mousemove', (e) => {
            const shapes = hero.querySelectorAll('.sv-shape');
            if (!shapes.length) return;
            const x = e.clientX / window.innerWidth;
            const y = e.clientY / window.innerHeight;
            shapes.forEach((shape, i) => {
                const speed = (i + 1) * 25;
                shape.style.transform = `translate(${(x - 0.5) * speed}px, ${(y - 0.5) * speed}px)`;
            });
        }, { passive: true });

        // Add concentric rings
        const wrapper = hero.querySelector('.sv-hero-image-wrapper');
        if (wrapper) {
            for (let i = 0; i < 3; i++) {
                const ring = document.createElement('div');
                ring.className = 'sv-hero-ring';
                wrapper.insertBefore(ring, wrapper.firstChild);
            }
        }

        // Floating particles
        const particleColors = ['#6C63FF', '#a855f7', '#FF6B6B', '#2ED573', '#FFC048'];
        const createParticle = () => {
            const particle = document.createElement('div');
            particle.className = 'sv-hero-particle';
            const sizes = ['sv-particle-sm', 'sv-particle-md', 'sv-particle-lg'];
            particle.classList.add(sizes[Math.floor(Math.random() * sizes.length)]);
            particle.style.background = particleColors[Math.floor(Math.random() * particleColors.length)];
            particle.style.left = Math.random() * 100 + '%';
            particle.style.bottom = '-10px';
            particle.style.opacity = '0';
            particle.style.animation = `svParticleRise ${3 + Math.random() * 4}s ease-out forwards`;
            hero.appendChild(particle);
            setTimeout(() => particle.remove(), 7000);
        };

        // Spawn particles periodically
        setInterval(() => {
            if (document.hidden) return;
            createParticle();
        }, 600);

        // Initial burst
        for (let i = 0; i < 8; i++) setTimeout(createParticle, i * 200);

        // Hero product card tilt on mouse move
        const heroCard = hero.querySelector('.sv-hero-product-card');
        if (heroCard) {
            hero.addEventListener('mousemove', (e) => {
                const rect = heroCard.getBoundingClientRect();
                const cardCenterX = rect.left + rect.width / 2;
                const cardCenterY = rect.top + rect.height / 2;
                const deltaX = (e.clientX - cardCenterX) / 40;
                const deltaY = (e.clientY - cardCenterY) / 40;
                heroCard.style.transform = `perspective(1000px) rotateY(${deltaX}deg) rotateX(${-deltaY}deg)`;
            });

            hero.addEventListener('mouseleave', () => {
                heroCard.style.transform = 'perspective(1000px) rotateY(0) rotateX(0)';
            });
        }
    }

    // =========================================================
    // 13. CURSOR SPOTLIGHT on dark sections
    // =========================================================
    if (!reduceMotion) {
        const darkSections = document.querySelectorAll('.sv-special-offer, .sv-newsletter');
        darkSections.forEach(section => {
            const spotlight = document.createElement('div');
            spotlight.className = 'sv-cursor-spotlight';
            section.appendChild(spotlight);

            section.addEventListener('mousemove', (e) => {
                const rect = section.getBoundingClientRect();
                spotlight.style.left = (e.clientX - rect.left) + 'px';
                spotlight.style.top = (e.clientY - rect.top) + 'px';
            });

            section.addEventListener('mouseenter', () => { spotlight.style.opacity = '1'; });
            section.addEventListener('mouseleave', () => { spotlight.style.opacity = '0'; });
        });
    }

    // =========================================================
    // 14. PROMO CARDS - mouse position gradient
    // =========================================================
    if (!reduceMotion) {
        document.querySelectorAll('.sv-promo-card').forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = ((e.clientX - rect.left) / rect.width) * 100;
                const y = ((e.clientY - rect.top) / rect.height) * 100;
                card.style.setProperty('--mouse-x', x + '%');
                card.style.setProperty('--mouse-y', y + '%');
            });
        });
    }

    // =========================================================
    // 15. RIPPLE EFFECT ON BUTTONS
    // =========================================================
    if (!reduceMotion) {
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.sv-btn');
            if (!btn) return;

            const ripple = document.createElement('span');
            const rect = btn.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;

            ripple.style.cssText = `
                position: absolute; width: ${size}px; height: ${size}px;
                left: ${x}px; top: ${y}px;
                background: rgba(255,255,255,0.3); border-radius: 50%;
                transform: scale(0); animation: svRippleEffect 0.6s linear;
                pointer-events: none;
            `;

            btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    }

    // =========================================================
    // 16. MAGNETIC BUTTON EFFECT
    // =========================================================
    if (!reduceMotion) {
        document.querySelectorAll('.sv-hero-btn').forEach(btn => {
            btn.addEventListener('mousemove', (e) => {
                const rect = btn.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                btn.style.transform = `translate(${x * 0.15}px, ${y * 0.15}px)`;
            });

            btn.addEventListener('mouseleave', () => {
                btn.style.transform = 'translate(0, 0)';
            });
        });
    }

    // =========================================================
    // 17. PRODUCT CARDS - cursor glow on hover
    // =========================================================
    if (!reduceMotion) {
        document.querySelectorAll('.sv-product-card').forEach(card => {
            card.addEventListener('mousemove', (e) => {
                const rect = card.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                card.style.background = `radial-gradient(circle 200px at ${x}px ${y}px, rgba(108, 99, 255, 0.04), #fff 80%)`;
            });

            card.addEventListener('mouseleave', () => {
                card.style.background = '#fff';
            });
        });
    }

    // =========================================================
    // 18. NEWSLETTER FORM
    // =========================================================
    const newsletterForm = document.getElementById('sv-newsletter-form');
    if (newsletterForm) {
        newsletterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = newsletterForm.querySelector('input').value;
            if (email) {
                window.svShowToast('Subscribed!', `Welcome! You'll receive updates at ${email}`, 'success');
                newsletterForm.reset();
            }
        });
    }

    // =========================================================
    // 19. SMOOTH SCROLL for anchor links
    // =========================================================
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', (e) => {
            const targetId = anchor.getAttribute('href');
            if (targetId === '#') return;
            const target = document.querySelector(targetId);
            if (target) {
                e.preventDefault();
                const headerHeight = document.querySelector('.site-header')?.offsetHeight || 0;
                window.scrollTo({
                    top: target.offsetTop - headerHeight - 20,
                    behavior: 'smooth'
                });
            }
        });
    });

    // =========================================================
    // 20. KEYBOARD NAVIGATION
    // =========================================================
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.body.style.overflow = '';
        }
    });

    // =========================================================
    // 21. HERO STATS HOVER - number wobble
    // =========================================================
    if (!reduceMotion) {
        document.querySelectorAll('.sv-hero-stat').forEach(stat => {
            stat.addEventListener('mouseenter', () => {
                const num = stat.querySelector('.sv-stat-number');
                if (num) {
                    num.style.transition = 'transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
                    num.style.transform = 'scale(1.2)';
                }
            });
            stat.addEventListener('mouseleave', () => {
                const num = stat.querySelector('.sv-stat-number');
                if (num) num.style.transform = 'scale(1)';
            });
        });
    }

    // =========================================================
    // 22. TESTIMONIAL CARDS - stagger star pop on scroll
    // =========================================================
    if (!reduceMotion) {
        const testimonialObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const stars = entry.target.querySelectorAll('.sv-testimonial-stars i');
                    stars.forEach((star, i) => {
                        star.style.opacity = '0';
                        star.style.transform = 'scale(0)';
                        setTimeout(() => {
                            star.style.transition = 'all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
                            star.style.opacity = '1';
                            star.style.transform = 'scale(1)';
                        }, i * 100);
                    });
                    testimonialObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        document.querySelectorAll('.sv-testimonial-card').forEach(card => testimonialObserver.observe(card));
    }

    // =========================================================
    // 23. SECTION ENTRANCE ANIMATIONS (background color sweep)
    // =========================================================
    if (!reduceMotion) {
        const sectionObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                    sectionObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.05 });

        document.querySelectorAll('.sv-categories-section, .sv-flash-deals, .sv-promo-banners, .sv-featured-products, .sv-brands-section, .sv-testimonials').forEach(section => {
            if (!section.closest('[data-sv-aos]')) {
                section.style.opacity = '0';
                section.style.transform = 'translateY(30px)';
                section.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
                sectionObserver.observe(section);
            }
        });
    }

    console.log('%c🛒 ShopVerse All Animations Loaded!', 'color: #6C63FF; font-size: 16px; font-weight: bold;');
});

/* Add ripple keyframes dynamically */
const svRippleStyle = document.createElement('style');
svRippleStyle.textContent = `@keyframes svRippleEffect { to { transform: scale(4); opacity: 0; } }`;
document.head.appendChild(svRippleStyle);
