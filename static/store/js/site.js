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

    // --- Desktop horizontal nav bar scroll ergonomics ---------------------
    const headerNavList = document.querySelector(".header-nav-list");
    if (headerNavList) {
        headerNavList.addEventListener(
            "wheel",
            (event) => {
                if (headerNavList.scrollWidth <= headerNavList.clientWidth) return;
                if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
                    event.preventDefault();
                    headerNavList.scrollLeft += event.deltaY;
                }
            },
            { passive: false }
        );
        const activeNavPill = headerNavList.querySelector(".nav-pill.active");
        if (activeNavPill && headerNavList.scrollWidth > headerNavList.clientWidth) {
            const listRect = headerNavList.getBoundingClientRect();
            const pillRect = activeNavPill.getBoundingClientRect();
            if (pillRect.right > listRect.right || pillRect.left < listRect.left) {
                activeNavPill.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
        }
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

    // --- Smart Match radio card selection sync -----------------------------
    document.querySelectorAll(".sm-option-input").forEach((radio) => {
        radio.addEventListener("change", () => {
            const group = radio.closest(".sm-options-grid");
            if (!group) return;
            group.querySelectorAll(".sm-option-card").forEach((card) => {
                const input = card.querySelector(".sm-option-input");
                card.classList.toggle("is-selected", Boolean(input && input.checked));
            });
        });
    });

    // --- Checkout phone number input guard ----------------------------------
    document.querySelectorAll('input[name="phone_number"]').forEach((phoneInput) => {
        phoneInput.addEventListener("input", () => {
            const raw = phoneInput.value;
            const startsWithPlus = raw.trimStart().startsWith("+");
            let cleaned = raw.replace(/[^\d\s\-+]/g, "");
            if (startsWithPlus) {
                cleaned = "+" + cleaned.replace(/\+/g, "");
            } else {
                cleaned = cleaned.replace(/\+/g, "");
            }
            const maxDigits = cleaned.startsWith("+91") ? 12 : startsWithPlus ? 12 : 10;
            let digitCount = 0;
            let result = "";
            for (const ch of cleaned) {
                if (/\d/.test(ch)) {
                    if (digitCount >= maxDigits) continue;
                    digitCount += 1;
                }
                result += ch;
            }
            if (result.length > 16) {
                result = result.slice(0, 16);
            }
            if (result !== raw) {
                phoneInput.value = result;
            }
        });
    });

    // --- Broken image safety net --------------------------------------------
    // Any storefront image that fails to load becomes a tidy placeholder
    // instead of a broken-image icon.
    bindImageFallbacks(document);

    // --- Submit feedback on key buttons (prevents double submits) -----------
    document.querySelectorAll("form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            const submitter = event.submitter;
            if (!submitter || submitter.type !== "submit" || submitter.dataset.noLoading) return;
            // Cart controls manage their own busy state in cart.js.
            if (
                submitter.classList.contains("quantity-button") ||
                submitter.matches("[data-cart-remove]")
            ) {
                return;
            }
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

// "Add to cart" forms use the same POST/CSRF protection as a normal submit, but
// with JavaScript we keep the shopper on the page and refresh only the counter
// in the header. Quantity changes and removals on the cart page itself are
// handled by cart.js, which talks to the same JSON endpoints without ever
// re-downloading the page.
const CART_ADD_FORM_SELECTOR = 'form[action*="/cart/add/"]';

document.addEventListener("submit", async (event) => {
    const form = event.target.closest ? event.target.closest(CART_ADD_FORM_SELECTOR) : null;
    if (!form || event.submitter?.name === "buy_now") return;
    // Ignore double clicks / double submits while a request is in flight.
    if (form.dataset.submitting === "1") {
        event.preventDefault();
        return;
    }
    event.preventDefault();

    const submitter = event.submitter || form.querySelector('button[type="submit"]');

    // Build the payload BEFORE the button is disabled: browsers leave a disabled
    // submit button out of FormData, and these forms carry an optional quantity
    // on the button itself.
    const payload = new FormData(form);
    if (submitter && submitter.name) {
        payload.set(submitter.name, submitter.value);
    }

    form.dataset.submitting = "1";
    if (submitter) submitter.disabled = true;
    try {
        // Same-origin fetch: the CSRF token travels in the form data and the
        // session cookie decides whose cart is being changed.
        const response = await fetch(form.action, {
            method: "POST",
            body: payload,
            headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            credentials: "same-origin",
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) {
            throw new Error(result.message || "We could not update your cart. Please try again.");
        }
        updateCartBadge(result.cart_count);
        showCartNotice(result.message, false);
    } catch (error) {
        showCartNotice(error.message || "We could not update your cart. Please try again.", true);
    } finally {
        form.dataset.submitting = "";
        if (submitter) submitter.disabled = false;
    }
});

function bindImageFallbacks(root) {
    const swapToPlaceholder = (img) => {
        const holder = document.createElement("div");
        holder.className = "placeholder-image";
        holder.innerHTML = '<i class="bi bi-image"></i><span>No image available</span>';
        img.replaceWith(holder);
    };
    root.querySelectorAll("img[data-fallback]").forEach((img) => {
        if (img.complete && img.naturalWidth === 0 && img.src) {
            swapToPlaceholder(img);
        } else {
            img.addEventListener("error", () => swapToPlaceholder(img), { once: true });
        }
    });
}

// Keep every cart counter in the chrome in sync: the header badge and the
// matching row inside the slide-out navigation drawer.
function updateCartBadge(count) {
    const cartLink = document.querySelector(".header-cart");
    const drawerLink = document.querySelector('.drawer-link[href*="/cart/"]');
    [
        [cartLink, "cart-badge"],
        [drawerLink, "drawer-badge"],
    ].forEach(([container, badgeClass]) => {
        if (!container) return;
        const badge = container.querySelector(`.${badgeClass}`);
        if (!count) {
            badge?.remove();
            return;
        }
        if (badge) {
            badge.textContent = count;
            return;
        }
        const next = document.createElement("span");
        next.className = badgeClass;
        next.textContent = count;
        container.appendChild(next);
    });
    if (cartLink) {
        cartLink.setAttribute("aria-label", count ? `Cart, ${count} items` : "Cart");
    }
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

// Shared storefront helpers. cart.js (loaded on the cart page only) reuses these
// so the header badge and the toast styling stay identical everywhere.
window.NorthstarStore = Object.assign(window.NorthstarStore || {}, {
    updateCartBadge,
    showCartNotice,
    bindImageFallbacks,
});
