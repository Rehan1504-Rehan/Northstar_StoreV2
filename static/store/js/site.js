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

// Add-to-cart uses the same POST/CSRF protection, but updates the page in place.
document.addEventListener("submit", async (event) => {
    const form = event.target.closest('form[action*="/cart/add/"], form[action*="/cart/update/"], form[action*="/cart/remove/"]');
    if (!form || event.submitter?.name === "buy_now") return;
    event.preventDefault();

    const button = event.submitter || form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    try {
        const response = await fetch(form.action, {
            method: "POST",
            body: new FormData(form, event.submitter || undefined),
            headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            credentials: "same-origin",
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || "Could not add this item to your cart.");

        updateCartBadge(result.cart_count);
        if (form.action.includes("/cart/update/") || form.action.includes("/cart/remove/")) {
            const response = await fetch(window.location.href, { credentials: "same-origin" });
            const html = await response.text();
            const nextDocument = new DOMParser().parseFromString(html, "text/html");
            const currentSection = document.querySelector("main .section-block");
            const nextSection = nextDocument.querySelector("main .section-block");
            if (currentSection && nextSection) currentSection.innerHTML = nextSection.innerHTML;
            const currentHero = document.querySelector(".page-hero-sub");
            const nextHero = nextDocument.querySelector(".page-hero-sub");
            if (currentHero && nextHero) currentHero.textContent = nextHero.textContent;
        }
        showCartNotice(result.message, false);
    } catch (error) {
        showCartNotice(error.message || "Unable to add this item. Please try again.", true);
    } finally {
        if (button) button.disabled = false;
    }
});

function updateCartBadge(count) {
    const cartLink = document.querySelector(".header-cart");
    if (!cartLink) return;
    let badge = cartLink.querySelector(".cart-badge");
    if (!count) {
        badge?.remove();
        cartLink.setAttribute("aria-label", "Cart");
        return;
    }
    if (!badge) {
        badge = document.createElement("span");
        badge.className = "cart-badge";
        cartLink.appendChild(badge);
    }
    badge.textContent = count;
    cartLink.setAttribute("aria-label", `Cart, ${count} items`);
}

function showCartNotice(message, isError) {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
        stack = document.createElement("div");
        stack.className = "container toast-stack";
        stack.setAttribute("aria-live", "polite");
        document.querySelector("main")?.prepend(stack);
    }
    const alert = document.createElement("div");
    alert.className = `alert ${isError ? "alert-danger" : "alert-success"} shadow-sm toast-alert`;
    alert.setAttribute("role", "status");
    alert.textContent = message;
    stack.replaceChildren(alert);
    window.setTimeout(() => alert.remove(), 4000);
}
