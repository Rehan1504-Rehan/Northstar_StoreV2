/* Northstar Store — asynchronous cart updates (cart page only).
 *
 * Every control on the cart page still lives inside a real POST form that
 * works with JavaScript switched off. This script upgrades those forms so a
 * quantity change or a removal talks to the Django JSON endpoint and repaints
 * only the numbers that changed — no page reload, no cart re-fetch, no images
 * reloaded.
 *
 * Requests are serialised per line and debounced, so holding down "+" sends at
 * most one request while one is already in flight, followed by a single request
 * carrying the final quantity.
 */
(function () {
    "use strict";

    var page = document.querySelector("[data-cart-page]");
    if (!page) return;

    var stateScript = document.getElementById("cart-state");
    var initialCart = readCartState(stateScript);

    function readCartState(script) {
        if (!script) return null;
        try {
            var parsed = JSON.parse(script.textContent || "null");
            return parsed && parsed.items ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    // Without a state snapshot the native forms are still perfectly usable, so
    // leave them alone rather than swallowing clicks.
    if (!initialCart) return;

    var DEBOUNCE_MS = 220;
    var REQUEST_TIMEOUT_MS = 15000;

    var helpers = window.NorthstarStore || {};
    var updateBadge = helpers.updateCartBadge || function () {};
    var notify = helpers.showCartNotice || function (message) { window.alert(message); };

    var layout = page.querySelector("[data-cart-layout]");
    var emptyState = document.getElementById("cartEmptyState");
    var reduceMotion = window.matchMedia
        ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
        : false;

    var numberFormat = new Intl.NumberFormat("en-IN", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    });

    var cart = initialCart;
    var lastServerCart = clone(initialCart);
    var lines = new Map();

    /* ------------------------------------------------------------------ */
    /* Formatting                                                          */
    /* ------------------------------------------------------------------ */

    // Mirrors the `inr` template filter: ₹ plus Indian digit grouping, with
    // paise only when they are not zero.
    function money(value) {
        var amount = Number(value);
        if (!isFinite(amount)) return "\u20b90";
        return "\u20b9" + numberFormat.format(round2(amount));
    }

    function round2(value) {
        return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function plural(count, singular, pluralForm) {
        return count === 1 ? singular : pluralForm || singular + "s";
    }

    /* ------------------------------------------------------------------ */
    /* Line registry                                                       */
    /* ------------------------------------------------------------------ */

    function lineFor(element) {
        var id = String(element.dataset.itemId);
        var line = lines.get(id);
        if (!line) {
            line = {
                id: id,
                el: element,
                quantityForm: element.querySelector("[data-cart-quantity-form]"),
                removeForm: element.querySelector("[data-cart-remove-form]"),
                quantityEl: element.querySelector("[data-line-quantity]"),
                subtotalEl: element.querySelector("[data-line-subtotal]"),
                decreaseButton: element.querySelector('[data-cart-step="-1"]'),
                increaseButton: element.querySelector('[data-cart-step="1"]'),
                spinner: element.querySelector("[data-line-spinner]"),
                statusText: element.querySelector("[data-line-status-text]"),
                pendingQuantity: null,
                timer: null,
                inFlight: false,
                dirty: false,
                removing: false,
            };
            lines.set(id, line);
        }
        return line;
    }

    page.querySelectorAll("[data-cart-line]").forEach(function (element) {
        var line = lineFor(element);
        var item = cart.items[line.id];
        line.pendingQuantity = item ? Number(item.quantity) : null;
    });

    /* ------------------------------------------------------------------ */
    /* Rendering                                                           */
    /* ------------------------------------------------------------------ */

    function renderCart(nextCart, options) {
        var opts = options || {};
        cart = nextCart;
        if (stateScript) stateScript.textContent = JSON.stringify(cart);

        var items = cart.items || {};
        lines.forEach(function (line) {
            var item = items[line.id];
            if (!item) {
                // The server no longer knows this line (product deleted, or it
                // was removed in another tab). Drop it from the page too.
                lines.delete(line.id);
                if (line.el) line.el.remove();
                return;
            }
            paintLine(line, item);
        });

        syncSummary(cart);

        if (Number(cart.item_count) > 0 && Number(cart.line_count) > 0) {
            hideEmptyState();
        } else {
            showEmptyState();
        }

        if (opts.flashId) {
            var flashed = lines.get(String(opts.flashId));
            if (flashed) pulse(flashed.subtotalEl);
        }
    }

    function paintLine(line, item) {
        var quantity = Number(item.quantity) || 0;
        // Do not overwrite a newer value the shopper asked for while a request
        // was in flight; that click still has to be sent.
        if (!line.inFlight && !line.dirty && !line.timer) {
            line.pendingQuantity = quantity;
        }
        if (line.quantityEl) line.quantityEl.textContent = String(quantity);
        if (line.subtotalEl) line.subtotalEl.textContent = money(item.subtotal);
        // Keep the no-JS fallback values current while we are here.
        if (line.decreaseButton) line.decreaseButton.value = String(Math.max(0, quantity - 1));
        if (line.increaseButton) line.increaseButton.value = String(quantity + 1);
        line.quantityEl && line.quantityEl.setAttribute("aria-label", "Quantity " + quantity);
    }

    function syncSummary(current) {
        setText("[data-cart-subtotal]", money(current.cart_regular_total));
        setText(
            "[data-cart-subtotal-label]",
            "Subtotal (" + current.item_count + " " + plural(Number(current.item_count), "item") + ")"
        );

        var savings = Number(current.cart_savings) || 0;
        var savingsRow = page.querySelector("[data-cart-savings-row]");
        var saveNote = page.querySelector("[data-cart-save-note]");
        if (savingsRow) {
            savingsRow.hidden = !(savings > 0);
            var savingsValue = savingsRow.querySelector("[data-cart-savings]");
            if (savingsValue) savingsValue.textContent = "\u2212" + money(savings);
        }
        if (saveNote) {
            saveNote.hidden = !(savings > 0);
            saveNote.textContent = "You save " + money(savings) + " on this order";
        }

        setText("[data-cart-total]", money(current.cart_total));

        // The hero sits above the cart section, outside [data-cart-page].
        var heroSub = document.querySelector("[data-cart-hero-sub]");
        if (heroSub) {
            var count = Number(current.item_count) || 0;
            heroSub.textContent = count
                ? count + " " + plural(count, "item") + " in your cart"
                : heroSub.dataset.emptyText || "";
        }

        updateBadge(Number(current.item_count) || 0);
    }

    function setText(selector, text) {
        var element = page.querySelector(selector);
        if (element) element.textContent = text;
    }

    function showEmptyState() {
        if (layout) layout.hidden = true;
        if (!emptyState) return;
        emptyState.hidden = false;
        // [data-reveal] elements start transparent and only get `.in` once the
        // scroll observer sees them; this one was hidden at the time, so add
        // the class by hand or the panel would stay invisible.
        emptyState.querySelectorAll("[data-reveal]").forEach(function (element) {
            element.classList.add("in");
        });
    }

    function hideEmptyState() {
        if (layout) layout.hidden = false;
        if (emptyState) emptyState.hidden = true;
    }

    function pulse(element) {
        if (!element || reduceMotion) return;
        element.classList.remove("value-pulse");
        // Read offsetWidth to restart the animation on a repeated change.
        void element.offsetWidth;
        element.classList.add("value-pulse");
        window.setTimeout(function () {
            element.classList.remove("value-pulse");
        }, 700);
    }

    function setBusy(line, busy, label) {
        if (!line.el) return;
        line.el.classList.toggle("is-busy", Boolean(busy));
        if (line.spinner) line.spinner.hidden = !busy;
        if (line.statusText) {
            line.statusText.textContent = busy ? label || "Updating cart" : "";
        }
        if (line.quantityForm) {
            line.quantityForm.setAttribute("aria-busy", busy ? "true" : "false");
        }
    }

    /* ------------------------------------------------------------------ */
    /* Local (optimistic) updates                                          */
    /* ------------------------------------------------------------------ */

    function setLocalQuantity(line, quantity) {
        var item = cart.items[line.id];
        if (!item) return;
        item.quantity = quantity;
        item.subtotal = round2(Number(item.unit_price) * quantity).toFixed(2);
        recomputeTotals(cart);
        renderCart(cart);
    }

    function recomputeTotals(target) {
        var itemCount = 0;
        var subtotal = 0;
        var regularTotal = 0;
        var items = target.items || {};
        Object.keys(items).forEach(function (id) {
            var item = items[id];
            var quantity = Number(item.quantity) || 0;
            itemCount += quantity;
            subtotal += Number(item.subtotal) || 0;
            regularTotal += (Number(item.list_price) || 0) * quantity;
        });
        subtotal = round2(subtotal);
        regularTotal = round2(regularTotal);
        target.item_count = itemCount;
        target.line_count = Object.keys(items).length;
        target.cart_total = subtotal.toFixed(2);
        target.cart_regular_total = regularTotal.toFixed(2);
        target.cart_savings = Math.max(0, round2(regularTotal - subtotal)).toFixed(2);
        target.shipping_free = subtotal > 999;
        target.shipping_label = target.shipping_free ? "FREE" : "Calculated at checkout";
        target.is_empty = target.line_count === 0;
    }

    function restoreLine(line) {
        var serverItem = lastServerCart && lastServerCart.items
            ? lastServerCart.items[line.id]
            : null;
        if (!serverItem || !cart.items[line.id]) return;
        cart.items[line.id] = clone(serverItem);
        recomputeTotals(cart);
        renderCart(cart);
    }

    /* ------------------------------------------------------------------ */
    /* Requests                                                            */
    /* ------------------------------------------------------------------ */

    function csrfToken(form) {
        var input = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input && input.value) return input.value;
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function CartRequestError(message, cartState) {
        this.name = "CartRequestError";
        this.message = message;
        this.cart = cartState || null;
    }
    CartRequestError.prototype = Object.create(Error.prototype);

    async function postForm(form, fields) {
        var body = new URLSearchParams();
        Object.keys(fields || {}).forEach(function (key) {
            body.set(key, fields[key]);
        });

        var controller = typeof AbortController === "function" ? new AbortController() : null;
        var timeout = controller
            ? window.setTimeout(function () {
                  controller.abort();
              }, REQUEST_TIMEOUT_MS)
            : null;

        var response;
        try {
            response = await fetch(form.action, {
                method: "POST",
                body: body,
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    Accept: "application/json",
                    "X-CSRFToken": csrfToken(form),
                },
                signal: controller ? controller.signal : undefined,
            });
        } catch (error) {
            throw new CartRequestError(
                error && error.name === "AbortError"
                    ? "That took too long. Check your connection and try again."
                    : "We could not reach the store. Check your connection and try again."
            );
        } finally {
            if (timeout) window.clearTimeout(timeout);
        }

        var payload = await response.json().catch(function () {
            return {};
        });

        if (!response.ok || !payload.ok) {
            var message = payload.message;
            if (!message) {
                message =
                    response.status === 403
                        ? "Your session expired. Refresh the page and try again."
                        : "We could not update your cart. Please try again.";
            }
            throw new CartRequestError(message, payload.cart);
        }
        return payload;
    }

    function applyServerPayload(payload, line) {
        if (!payload || !payload.cart) return;
        lastServerCart = clone(payload.cart);
        var flashId = line ? line.id : null;
        renderCart(payload.cart, { flashId: flashId });
        if (!line || payload.cart.items[line.id] === undefined) return;

        var serverQuantity = Number(payload.cart.items[line.id].quantity);
        if (
            line.pendingQuantity !== null &&
            line.pendingQuantity !== serverQuantity &&
            !line.removing
        ) {
            // A click landed while this request was in flight: keep showing the
            // shopper's newest value; the follow-up request settles it.
            setLocalQuantity(line, line.pendingQuantity);
        } else {
            line.pendingQuantity = serverQuantity;
        }
    }

    function handleFailure(error, line) {
        notify(error.message || "We could not update your cart. Please try again.", true);
        if (error.cart) {
            lastServerCart = clone(error.cart);
            renderCart(error.cart);
        } else if (line) {
            restoreLine(line);
        }
        if (line && cart.items[line.id]) {
            line.pendingQuantity = Number(cart.items[line.id].quantity);
        }
    }

    /* ------------------------------------------------------------------ */
    /* Quantity stepper                                                    */
    /* ------------------------------------------------------------------ */

    function handleStep(line, step) {
        if (!step || line.removing) return;
        var item = cart.items[line.id];
        if (!item) return;

        var quantity = Number(item.quantity) || 0;
        var next = quantity + step;
        if (next < 0) return;
        // Minus at one removes the line, exactly as the server-rendered form
        // has always done (it posted a quantity of zero).
        if (next === 0) {
            handleRemove(line);
            return;
        }

        var stock = Number(item.stock);
        if (isFinite(stock) && next > stock) {
            notify(
                "Only " + stock + " " + plural(stock, "item") + " of this product " +
                    (stock === 1 ? "is" : "are") + " in stock.",
                true
            );
            return;
        }

        // Remember the value the shopper asked for before repainting: if a
        // request is already in flight this is what the follow-up will send.
        line.pendingQuantity = next;
        setLocalQuantity(line, next);
        setBusy(line, true);
        scheduleFlush(line);
    }

    function scheduleFlush(line) {
        if (line.timer) window.clearTimeout(line.timer);
        line.timer = window.setTimeout(function () {
            line.timer = null;
            flushQuantity(line);
        }, DEBOUNCE_MS);
    }

    async function flushQuantity(line) {
        if (line.removing) return;
        if (line.inFlight) {
            // A newer click arrived while the request was in flight; send the
            // final value as soon as the current response lands.
            line.dirty = true;
            return;
        }
        if (!line.quantityForm || line.pendingQuantity === null) return;

        line.inFlight = true;
        line.dirty = false;
        setBusy(line, true);

        try {
            var payload = await postForm(line.quantityForm, {
                quantity: String(line.pendingQuantity),
            });
            applyServerPayload(payload, line);
        } catch (error) {
            handleFailure(error, line);
        } finally {
            line.inFlight = false;
            if (!line.removing) {
                if (line.dirty) {
                    // Send the value the shopper settled on while we were busy.
                    line.dirty = false;
                    flushQuantity(line);
                } else if (!line.timer) {
                    var settled = cart.items[line.id];
                    if (settled) line.pendingQuantity = Number(settled.quantity);
                    setBusy(line, false);
                }
            }
        }
    }

    /* ------------------------------------------------------------------ */
    /* Remove                                                              */
    /* ------------------------------------------------------------------ */

    function handleRemove(line) {
        if (line.removing || !line.removeForm) return;
        line.removing = true;
        if (line.timer) {
            window.clearTimeout(line.timer);
            line.timer = null;
        }
        if (line.el) line.el.classList.add("is-removing");
        setBusy(line, true, "Removing item");
        removeRemote(line);
    }

    async function removeRemote(line) {
        try {
            var payload = await postForm(line.removeForm, {});
            lastServerCart = clone(payload.cart);
            lines.delete(line.id);
            renderCart(payload.cart);
            if (line.el && line.el.isConnected) line.el.remove();
            notify(payload.message || "Item removed from your cart.", false);
        } catch (error) {
            line.removing = false;
            if (line.el) line.el.classList.remove("is-removing");
            notify(error.message || "We could not remove that item. Please try again.", true);
            if (error.cart) {
                lastServerCart = clone(error.cart);
                renderCart(error.cart);
            }
        } finally {
            if (!line.removing) setBusy(line, false);
        }
    }

    /* ------------------------------------------------------------------ */
    /* Wiring                                                              */
    /* ------------------------------------------------------------------ */

    page.addEventListener("click", function (event) {
        var target = event.target;
        if (!target || !target.closest) return;

        var stepButton = target.closest("[data-cart-step]");
        if (stepButton && page.contains(stepButton)) {
            var stepLine = stepButton.closest("[data-cart-line]");
            if (!stepLine) return;
            event.preventDefault();
            handleStep(lineFor(stepLine), Number(stepButton.dataset.cartStep));
            return;
        }

        var removeButton = target.closest("[data-cart-remove]");
        if (removeButton && page.contains(removeButton)) {
            var removeLine = removeButton.closest("[data-cart-line]");
            if (!removeLine) return;
            event.preventDefault();
            handleRemove(lineFor(removeLine));
        }
    });

    // Keyboard submits (Enter on a focused button) do not produce a click on
    // every browser, so mirror the same behaviour from the submit event.
    page.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches) return;
        if (!form.matches("[data-cart-quantity-form], [data-cart-remove-form]")) return;
        event.preventDefault();

        var lineEl = form.closest("[data-cart-line]");
        if (!lineEl) return;
        var line = lineFor(lineEl);

        if (form.matches("[data-cart-remove-form]")) {
            handleRemove(line);
            return;
        }

        var submitter = event.submitter;
        var step = submitter && submitter.dataset.cartStep
            ? Number(submitter.dataset.cartStep)
            : 0;
        if (step) handleStep(line, step);
    });

    // Make sure the initial render agrees with the embedded state (covering a
    // page restored from the back/forward cache with stale markup).
    renderCart(cart);
})();
