/* Northstar Store — storefront interactions (vanilla JS, no libraries). */
document.addEventListener("DOMContentLoaded", () => {
    const reduceMotion =
        window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // --- Header shadow once the page scrolls a little ---------------------
    const header = document.querySelector(".site-header");
    if (header) {
        const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 10);
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
    }

    // --- Left slide navigation drawer -------------------------------------
    const drawer = document.getElementById("navDrawer");
    const overlay = document.getElementById("navOverlay");
    const openers = document.querySelectorAll("[data-nav-open]");
    const accordionBtn = document.querySelector("[data-nav-accordion]");
    const accordionPanel = document.getElementById("navCategories");
    let previousOverflow = "";
    let previousPadding = "";

    if (drawer) {
        drawer.inert = true;
    }

    const setNavOpen = (open) => {
        if (!drawer || !overlay) return;
        drawer.classList.toggle("is-open", open);
        overlay.classList.toggle("is-open", open);
        document.documentElement.classList.toggle("nav-lock", open);
        document.body.classList.toggle("nav-lock", open);
        drawer.setAttribute("aria-hidden", open ? "false" : "true");
        drawer.inert = !open;
        openers.forEach((btn) => btn.setAttribute("aria-expanded", open ? "true" : "false"));
        if (open) {
            previousOverflow = document.body.style.overflow;
            previousPadding = document.body.style.paddingRight;
            const scrollbar = window.innerWidth - document.documentElement.clientWidth;
            document.body.style.overflow = "hidden";
            if (scrollbar > 0) {
                document.body.style.paddingRight = `${scrollbar}px`;
            }
            const closeBtn = drawer.querySelector("[data-nav-close]");
            if (closeBtn) closeBtn.focus();
        } else {
            document.body.style.overflow = previousOverflow;
            document.body.style.paddingRight = previousPadding;
        }
    };

    openers.forEach((btn) => {
        btn.addEventListener("click", () => setNavOpen(true));
    });
    document.querySelectorAll("[data-nav-close]").forEach((el) => {
        el.addEventListener("click", () => setNavOpen(false));
    });
    drawer &&
        drawer.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => setNavOpen(false));
        });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && drawer && drawer.classList.contains("is-open")) {
            setNavOpen(false);
        }
    });

    if (accordionBtn && accordionPanel) {
        const setAccordion = (expanded) => {
            accordionBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
            accordionBtn.classList.toggle("is-expanded", expanded);
            accordionPanel.hidden = !expanded;
        };
        accordionBtn.addEventListener("click", () => {
            setAccordion(accordionBtn.getAttribute("aria-expanded") !== "true");
        });
        if (accordionBtn.dataset.navAccordionOpen === "true") {
            setAccordion(true);
        }
    }

    // --- Account menu (top-right avatar) -----------------------------------
    // Bootstrap's dropdown plugin normally handles this. This fallback keeps
    // the menu hidden by default and toggles it on click when Bootstrap's JS
    // is unavailable, so the box is never stuck open.
    const accountBtn = document.getElementById("accountMenuBtn");
    const accountMenu = document.getElementById("accountMenu");
    if (accountBtn && accountMenu && !(window.bootstrap && window.bootstrap.Dropdown)) {
        const setAccountOpen = (open) => {
            accountMenu.classList.toggle("show", open);
            accountBtn.classList.toggle("show", open);
            accountBtn.setAttribute("aria-expanded", open ? "true" : "false");
        };
        setAccountOpen(false);
        accountBtn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            setAccountOpen(!accountMenu.classList.contains("show"));
        });
        document.addEventListener("click", (event) => {
            if (!accountMenu.contains(event.target) && !accountBtn.contains(event.target)) {
                setAccountOpen(false);
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && accountMenu.classList.contains("show")) {
                setAccountOpen(false);
                accountBtn.focus();
            }
        });
    }

    // --- Scroll-in reveal animations ---------------------------------------
    const revealEls = document.querySelectorAll("[data-reveal]");
    if (reduceMotion || !("IntersectionObserver" in window)) {
        revealEls.forEach((el) => el.classList.add("in"));
    } else {
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("in");
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.12, rootMargin: "0px 0px -34px 0px" }
        );
        revealEls.forEach((el) => observer.observe(el));
    }

    // --- Quantity steppers (product detail) --------------------------------
    document.querySelectorAll("[data-quantity-action]").forEach((button) => {
        button.addEventListener("click", () => {
            const control = button.closest(".quantity-control");
            const input = control && control.querySelector("input");
            if (!input) return;
            const minimum = Number(input.min || 1);
            const maximum = Number(input.max || Number.MAX_SAFE_INTEGER);
            const current = Number(input.value || minimum);
            const direction = button.dataset.quantityAction === "increase" ? 1 : -1;
            input.value = Math.min(maximum, Math.max(minimum, current + direction));
        });
    });

    // --- Show / hide password buttons ---------------------------------------
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const input = document.getElementById(button.dataset.passwordToggle);
            if (!input) return;
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
            const icon = button.querySelector("i");
            if (icon) {
                icon.className = showing ? "bi bi-eye" : "bi bi-eye-slash";
            }
        });
    });

    // --- Broken image safety net --------------------------------------------
    // Any storefront image that fails to load becomes a tidy placeholder
    // instead of a broken-image icon.
    const swapToPlaceholder = (img) => {
        const holder = document.createElement("div");
        holder.className = "placeholder-image";
        holder.innerHTML = '<i class="bi bi-image"></i><span>No image available</span>';
        img.replaceWith(holder);
    };
    document.querySelectorAll("img[data-fallback]").forEach((img) => {
        if (img.complete && img.naturalWidth === 0 && img.src) {
            swapToPlaceholder(img);
        } else {
            img.addEventListener("error", () => swapToPlaceholder(img), { once: true });
        }
    });

    // --- Submit feedback on key buttons (prevents double submits) -----------
    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const submitter = event.submitter;
            if (!submitter || submitter.type !== "submit" || submitter.dataset.noLoading) return;
            if (submitter.classList.contains("quantity-button")) return;
            submitter.classList.add("is-loading");
            submitter.style.pointerEvents = "none";
            window.setTimeout(() => {
                submitter.classList.remove("is-loading");
                submitter.style.pointerEvents = "";
            }, 4000);
        });
    });

    // --- Give temporary alerts a gentle auto close ---------------------------
    window.setTimeout(() => {
        document.querySelectorAll(".alert-dismissible").forEach((alert) => {
            if (window.bootstrap) {
                window.bootstrap.Alert.getOrCreateInstance(alert).close();
            }
        });
    }, 6500);
});
