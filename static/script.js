// Single Page Application JavaScript

document.getElementById("saleForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const customer = document.getElementById("customer").value;
    const itemElement = document.getElementById("item");
    const item = itemElement.value;
    const price = itemElement.options[itemElement.selectedIndex].getAttribute("data-price");
    const quantity = document.getElementById("quantity").value;

    try {
        const response = await fetch("/api/add-sale", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({customer, item, price, quantity})
        });

        const result = await response.json();
        
        if (result.success) {
            loadSales();
            e.target.reset();
        } else {
            alert('Error adding sale: ' + result.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
});

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

            if (!itemCount[sale.item]) itemCount[sale.item] = 0;
            itemCount[sale.item] += sale.quantity;

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

        // Best Seller Logic
        let bestSeller = "None";
        if (Object.keys(itemCount).length > 0) {
            bestSeller = Object.keys(itemCount).reduce((a, b) => itemCount[a] > itemCount[b] ? a : b);
        }

        document.getElementById("bestSeller").textContent = bestSeller;
    } catch (error) {
        console.error('Error loading sales:', error);
    }
}

// Load sales when page loads
loadSales();

// Dropdown functionality for other pages
function toggleDropdown(id) {
    // Handle both with and without 'dropdown-' prefix
    const fullId = id.startsWith('dropdown-') ? id : 'dropdown-' + id;
    
    // Remove active class from all rows
    document.querySelectorAll('tr.dropdown-active').forEach(row => {
        row.classList.remove('dropdown-active');
    });
    
    // Close all other dropdowns
    document.querySelectorAll('.dropdown-content').forEach(dropdown => {
        if (dropdown.id !== fullId) {
            dropdown.classList.remove('show');
        }
    });

    // Toggle the clicked dropdown
    const clickedDropdown = document.getElementById(fullId);
    if (clickedDropdown) {
        clickedDropdown.classList.toggle('show');
        
        // Add active class to parent row if dropdown is now open
        if (clickedDropdown.classList.contains('show')) {
            const parentRow = clickedDropdown.closest('tr');
            if (parentRow) {
                parentRow.classList.add('dropdown-active');
            }
        }
    }
}

// Close dropdowns when clicking outside
window.onclick = function(event) {
    if (!event.target.closest('.actions-menu')) {
        document.querySelectorAll('.dropdown-content').forEach(dropdown => {
            dropdown.classList.remove('show');
        });
        document.querySelectorAll('tr.dropdown-active').forEach(row => {
            row.classList.remove('dropdown-active');
        });
    }
}