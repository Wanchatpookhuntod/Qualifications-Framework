/*
 * Background autosave for the instructor TQF editors (มคอ.3/4/5).
 *
 * Activates on any <form data-autosave> on the page. Periodically POSTs the
 * whole form back to its own URL with action=autosave, so half-filled data is
 * not lost when the user navigates away, closes the tab, or the session ends.
 *
 * The server keeps the document status unchanged for action=autosave (no
 * DRAFT/SUBMITTED transition, no flash, no redirect) and replies with JSON.
 * No build step / framework – vanilla JS only.
 */
(function () {
    "use strict";

    var form = document.querySelector("form[data-autosave]");
    if (!form) {
        return;
    }

    var url = form.getAttribute("action") || window.location.href;
    var indicator = document.getElementById("autosaveStatus");
    var INTERVAL_MS = 15000;   // periodic backstop
    var DEBOUNCE_MS = 1500;    // quick save shortly after the user stops editing

    var dirty = false;        // unsaved edits since last successful save
    var saving = false;       // an autosave request is in flight
    var submitting = false;   // a real draft/submit is in progress
    var locked = false;       // server said the doc can no longer be edited
    var debounceTimer = null; // pending quick-save after the latest edit

    function setStatus(text, cls) {
        if (!indicator) {
            return;
        }
        indicator.textContent = text;
        indicator.className = "autosave-status" + (cls ? " " + cls : "");
    }

    function nowLabel() {
        var d = new Date();
        var hh = String(d.getHours()).padStart(2, "0");
        var mm = String(d.getMinutes()).padStart(2, "0");
        return hh + ":" + mm;
    }

    function markDirty() {
        if (locked || submitting) {
            return;
        }
        dirty = true;
        // Persist quickly after editing stops, so a refresh shortly after won't
        // lose the change (the 15s interval alone left too wide a window).
        if (debounceTimer) {
            window.clearTimeout(debounceTimer);
        }
        debounceTimer = window.setTimeout(function () {
            debounceTimer = null;
            autosave();
        }, DEBOUNCE_MS);
    }

    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);

    // A real "บันทึกฉบับร่าง" / "ส่ง" submit owns the data from here on; stop autosaving.
    form.addEventListener("submit", function () {
        submitting = true;
    });

    function buildPayload() {
        var fd = new FormData(form);
        fd.set("action", "autosave"); // override; submit buttons are not included by FormData(form)
        return fd;
    }

    function autosave() {
        if (locked || submitting || saving || !dirty) {
            return;
        }
        saving = true;
        setStatus("กำลังบันทึกอัตโนมัติ…");
        fetch(url, {
            method: "POST",
            body: buildPayload(),
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
        })
            .then(function (res) {
                if (res.status === 409) {
                    locked = true;
                    setStatus("เอกสารถูกล็อก ไม่บันทึกอัตโนมัติแล้ว", "is-warning");
                    return null;
                }
                if (!res.ok) {
                    throw new Error("HTTP " + res.status);
                }
                return res.json();
            })
            .then(function (data) {
                if (data && data.ok) {
                    dirty = false;
                    setStatus("บันทึกอัตโนมัติแล้ว " + nowLabel(), "is-ok");
                }
            })
            .catch(function () {
                setStatus("บันทึกอัตโนมัติไม่สำเร็จ – โปรดกดบันทึกฉบับร่างเอง", "is-error");
            })
            .finally(function () {
                saving = false;
            });
    }

    var timer = window.setInterval(autosave, INTERVAL_MS);

    // Best-effort final save when the page is being hidden/closed/refreshed or
    // navigated away. `pagehide` fires reliably on reload and navigation (unlike
    // `visibilitychange`, which a plain browser refresh may skip), so binding
    // both is what keeps a refresh from dropping the last few edits.
    function flush() {
        if (locked || submitting || !dirty || saving) {
            return;
        }
        if (navigator.sendBeacon && navigator.sendBeacon(url, buildPayload())) {
            dirty = false;
        }
    }

    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            flush();
        }
    });

    window.addEventListener("pagehide", flush);

    window.addEventListener("beforeunload", function () {
        flush();
        window.clearInterval(timer);
    });
})();
