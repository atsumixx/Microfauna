document.getElementById("saleForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const customer = document.getElementById("customer").value;
    const itemElement = document.getElementById("item");
    const item = itemElement.value;
    const price = itemElement.options[itemElement.selectedIndex].getAttribute("data-price");
    const quantity = document.getElementById("quantity").value;

    await fetch("/add-sale", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({customer, item, price, quantity})
    });

    loadSales();
    e.target.reset();
});


async function loadSales() {
    const res = await fetch("/get-sales");
    const data = await res.json();

    const table = document.getElementById("salesTable");
    table.innerHTML = "";

    let totalRevenue = 0;
    let itemCount = {};
    let totalSales = data.length;

    data.forEach(sale => {
        totalRevenue += sale.total;

        if (!itemCount[sale.item]) itemCount[sale.item] = 0;
        itemCount[sale.item] += sale.quantity;

        table.innerHTML += `
            <tr>
                <td>${sale.customer}</td>
                <td>${sale.item}</td>
                <td>${sale.quantity}</td>
                <td>₱${sale.total}</td>
                <td>${sale.timestamp}</td>
            </tr>
        `;
    });

    document.getElementById("totalRevenue").textContent = `₱${totalRevenue}`;
    document.getElementById("totalSalesCount").textContent = totalSales;

    // Best Seller Logic
    let bestSeller = "None";
    if (Object.keys(itemCount).length > 0) {
        bestSeller = Object.keys(itemCount).reduce((a, b) => itemCount[a] > itemCount[b] ? a : b);
    }

    document.getElementById("bestSeller").textContent = bestSeller;
}

loadSales();

function toggleDropdown(id) {
    const dropdown = document.getElementById(id);
    dropdown.classList.toggle('show');
}

// Close only if clicked outside dropdown or button
window.onclick = function(event) {
    if (!event.target.closest('.actions-menu')) {
        document.querySelectorAll('.dropdown-content').forEach(dropdown => {
            dropdown.classList.remove('show');
        });
    }
}
