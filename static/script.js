// --- Add Sale Form Submission ---
document.getElementById("saleForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const customer = document.getElementById("customer").value;
    const itemElement = document.getElementById("item");
    const item = itemElement.value;
    const price = parseFloat(itemElement.options[itemElement.selectedIndex].getAttribute("data-price"));
    const quantity = parseInt(document.getElementById("quantity").value);

    if (!customer || !item || quantity <= 0) {
        alert("Please fill all fields correctly.");
        return;
    }

    try {
        const response = await fetch("/api/add-sale", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ customer, item, price, quantity })
        });

        const result = await response.json();
        
        if (result.success) {
            loadSales(); // Refresh table and stats
            e.target.reset(); // Reset form
        } else {
            alert('Error adding sale: ' + result.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
});

// --- Load Sales and Dashboard Stats ---
async function loadSales() {
    try {
        const res = await fetch("/api/get-sales");
        const data = await res.json();

        const table = document.getElementById("salesTable");
        table.innerHTML = "";

        let totalRevenue = 0;
        let itemCount = {};
        let totalSales = data.length;

        data.forEach(sale => {
            totalRevenue += sale.total;

            itemCount[sale.item] = (itemCount[sale.item] || 0) + sale.quantity;

            table.innerHTML += `
                <tr>
                    <td>${sale.customer}</td>
                    <td>${sale.item}</td>
                    <td>${sale.quantity}</td>
                    <td>₱${sale.total.toFixed(2)}</td>
                    <td>${sale.timestamp}</td>
                </tr>
            `;
        });

        document.getElementById("totalRevenue").textContent = `₱${totalRevenue.toFixed(2)}`;
        document.getElementById("totalSalesCount").textContent = totalSales;

        // Determine best seller
        let bestSeller = "None";
        if (Object.keys(itemCount).length > 0) {
            bestSeller = Object.keys(itemCount).reduce((a, b) => itemCount[a] > itemCount[b] ? a : b);
        }
        document.getElementById("bestSeller").textContent = bestSeller;
    } catch (error) {
        console.error('Error loading sales:', error);
    }
}

// --- Dropdown Menu Logic ---
function toggleDropdown(id) {
    const fullId = id.startsWith('dropdown-') ? id : 'dropdown-' + id;

    // Close other dropdowns
    document.querySelectorAll('.dropdown-content').forEach(dropdown => {
        if (dropdown.id !== fullId) {
            dropdown.classList.remove('show');
        }
    });

    // Remove active class from other rows
    document.querySelectorAll('tr.dropdown-active').forEach(row => {
        row.classList.remove('dropdown-active');
    });

    // Toggle clicked dropdown
    const clickedDropdown = document.getElementById(fullId);
    if (clickedDropdown) {
        clickedDropdown.classList.toggle('show');

        // Highlight parent row if dropdown is open
        if (clickedDropdown.classList.contains('show')) {
            const parentRow = clickedDropdown.closest('tr');
            if (parentRow) parentRow.classList.add('dropdown-active');
        }
    }
}

// Close dropdowns if clicking outside
window.onclick = function(event) {
    if (!event.target.closest('.actions-menu')) {
        document.querySelectorAll('.dropdown-content').forEach(dropdown => dropdown.classList.remove('show'));
        document.querySelectorAll('tr.dropdown-active').forEach(row => row.classList.remove('dropdown-active'));
    }
}

// --- Initialize ---
loadSales();
