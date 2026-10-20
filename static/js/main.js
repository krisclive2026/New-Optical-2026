// OSMS Main JavaScript File

document.addEventListener("DOMContentLoaded", function () {
    console.log("VisionCraft OSMS initialized.");

    // Auto-dismiss alert toasts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Order Calculation logic
    setupOrderCalculations();

    // Table Quick Filter logic
    setupTableFilters();

    // Delete confirmation modals setup
    setupDeleteConfirmations();
});

// Calculate Order & Invoice totals in real-time
function setupOrderCalculations() {
    const frameSelect = document.getElementById("order-frame-select");
    const lensSelect = document.getElementById("order-lens-select");
    const qtyInput = document.getElementById("order-qty");
    const otherChargesInput = document.getElementById("order-other-charges");
    const discountInput = document.getElementById("order-discount");
    const advanceInput = document.getElementById("order-advance");
    const taxRateInput = document.getElementById("invoice-tax-rate");

    const framePriceEl = document.getElementById("display-frame-price");
    const lensPriceEl = document.getElementById("display-lens-price");
    const subtotalEl = document.getElementById("display-subtotal");
    const taxAmountEl = document.getElementById("display-tax-amount");
    const totalEl = document.getElementById("display-total");
    const balanceEl = document.getElementById("display-balance");

    const totalHidden = document.getElementById("input-total-amount");
    const balanceHidden = document.getElementById("input-balance-amount");

    function calculateTotals() {
        let framePrice = 0.0;
        let lensPrice = 0.0;

        if (frameSelect && frameSelect.selectedIndex > 0) {
            const selectedOption = frameSelect.options[frameSelect.selectedIndex];
            framePrice = parseFloat(selectedOption.getAttribute("data-price") || 0.0);
        }

        if (lensSelect && lensSelect.selectedIndex > 0) {
            const selectedOption = lensSelect.options[lensSelect.selectedIndex];
            lensPrice = parseFloat(selectedOption.getAttribute("data-price") || 0.0);
        }

        const qty = parseInt(qtyInput ? qtyInput.value : 1) || 1;
        const otherCharges = parseFloat(otherChargesInput ? otherChargesInput.value : 0.0) || 0.0;
        const discount = parseFloat(discountInput ? discountInput.value : 0.0) || 0.0;
        const advance = parseFloat(advanceInput ? advanceInput.value : 0.0) || 0.0;
        const taxRate = parseFloat(taxRateInput ? taxRateInput.value : 0.0) || 0.0;

        const subtotal = framePrice + (lensPrice * qty) + otherCharges - discount;
        const cleanSubtotal = subtotal > 0 ? subtotal : 0.0;

        const taxAmount = (cleanSubtotal * taxRate) / 100.0;
        const grandTotal = cleanSubtotal + taxAmount;
        let balance = grandTotal - advance;
        if (balance < 0) balance = 0.0;

        if (framePriceEl) framePriceEl.textContent = "₹" + framePrice.toFixed(2);
        if (lensPriceEl) lensPriceEl.textContent = "₹" + (lensPrice * qty).toFixed(2);
        if (subtotalEl) subtotalEl.textContent = "₹" + cleanSubtotal.toFixed(2);
        if (taxAmountEl) taxAmountEl.textContent = "₹" + taxAmount.toFixed(2);
        if (totalEl) totalEl.textContent = "₹" + grandTotal.toFixed(2);
        if (balanceEl) balanceEl.textContent = "₹" + balance.toFixed(2);

        if (totalHidden) totalHidden.value = grandTotal.toFixed(2);
        if (balanceHidden) balanceHidden.value = balance.toFixed(2);
    }

    if (frameSelect) frameSelect.addEventListener("change", calculateTotals);
    if (lensSelect) lensSelect.addEventListener("change", calculateTotals);
    if (qtyInput) qtyInput.addEventListener("input", calculateTotals);
    if (otherChargesInput) otherChargesInput.addEventListener("input", calculateTotals);
    if (discountInput) discountInput.addEventListener("input", calculateTotals);
    if (advanceInput) advanceInput.addEventListener("input", calculateTotals);
    if (taxRateInput) taxRateInput.addEventListener("input", calculateTotals);

    // Initial run
    calculateTotals();
}

// Client-side quick filter for tables
function setupTableFilters() {
    const searchInputs = document.querySelectorAll(".table-search-input");
    searchInputs.forEach(function (input) {
        input.addEventListener("keyup", function () {
            const filter = this.value.toLowerCase();
            const targetTableId = this.getAttribute("data-target");
            const table = document.getElementById(targetTableId);
            if (!table) return;

            const trs = table.getElementsByTagName("tr");
            for (let i = 1; i < trs.length; i++) {
                const tr = trs[i];
                const textContent = tr.textContent || tr.innerText;
                if (textContent.toLowerCase().indexOf(filter) > -1) {
                    tr.style.display = "";
                } else {
                    tr.style.display = "none";
                }
            }
        });
    });
}

// Setup confirmation before destructive operations
function setupDeleteConfirmations() {
    const deleteButtons = document.querySelectorAll(".btn-delete-confirm");
    deleteButtons.forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            const message = this.getAttribute("data-message") || "Are you sure you want to delete this item?";
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}
