async function fetchData(url) {
    const response = await fetch(url);
    return response.json();
}

let weeklyChartInstance = null;
let dayChartInstance = null;
let mainChartInstance = null;

async function renderWeeklyChart() {
    const data = await fetchData("/weekly-data");
    const ctx = document.getElementById("weekChart").getContext("2d");

    if (weeklyChartInstance) {
        weeklyChartInstance.destroy();
    }

    weeklyChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: Object.keys(data),
            datasets: [
                {
                    label: "Number of news",
                    data: Object.values(data),
                    borderColor: "#4f46e5",
                    fill: false,
                },
            ],
        },
        options: { responsive: true },
    });
}

async function renderDayChart(date) {
    const data = await fetchData(`/daily-data?date=${date}`);
    const ctx = document.getElementById("dayChart").getContext("2d");
    if (dayChartInstance) {
        dayChartInstance.destroy();
    }

    dayChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels: Object.keys(data),
            datasets: [
                {
                    label: `News for ${date}`,
                    data: Object.values(data),
                    backgroundColor: "#4f46e5",
                },
            ],
        },
        options: { responsive: true },
    });
    ctx.classList.add("visible");
}

document
    .getElementById("filterBtn")
    .addEventListener("click", async function () {
        const category = document.getElementById("categoryFilter").value;
        const date = document.getElementById("chartDate").value;
        if (!category || !date) {
            alert("Select category and date");
            return;
        }
        const newsData = await fetchData(
            `/news-by-category-and-date?category=${category}&date=${date}`
        );
        const newsContainer = document.getElementById("newsContainer");
        newsContainer.innerHTML = "";

        if (newsData.length === 0) {
            newsContainer.innerHTML = "<p>No data</p>";
            newsContainer.style.display = "block";
            return;
        }

        newsData.forEach((news) => {
            const div = document.createElement("div");
            div.classList.add("news-item");
            div.innerHTML = `<h3>${news.title}</h3><p>${news.description}</p><div class="card-link-container"><a href="${news.url}" target="_blank">Read more</a></div>`;
            newsContainer.appendChild(div);
        });
        newsContainer.style.display = "grid";
    });

async function loadNewsByDate(date) {
    const newsContainer = document.getElementById("newsContainer");
    newsContainer.innerHTML = "";
    const newsData = await fetchData(`/news-by-date?date=${date}`);

    if (newsData.length === 0) {
        newsContainer.innerHTML = "<p>No data</p>";
        return;
    }

    newsData.forEach((news) => {
        const div = document.createElement("div");
        div.classList.add("news-item");
        div.innerHTML = `<h3>${news.title}</h3><p>${news.description}</p><a href="${news.url}" target="_blank">Read more</a>`;
        newsContainer.appendChild(div);
    });
}

document
    .getElementById("loadDayChart")
    .addEventListener("click", async function () {
        const date = document.getElementById("chartDate").value;
        if (!date) return;
        await renderDayChart(date);
        await loadNewsByDate(date);
    });

document
    .getElementById("reportForm")
    .addEventListener("submit", async function (event) {
        event.preventDefault();
        const date = document.getElementById("date").value;
        const email = document.getElementById("email").value;
        const loaderAnimation = document.getElementById("loaderAnimation");
        loaderAnimation.classList.remove("report-non-visible");
        loaderAnimation.classList.add("report-visible");
        const response = await fetch("/send-report", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: `date=${date}&email=${email}`,
        });
        const result = await response.json();
        document.getElementById("status").innerText = result.message;
        loaderAnimation.classList.remove("report-visible");
        loaderAnimation.classList.add("report-non-visible");
    });
// Рендеримо графіки при завантаженні сторінки
renderWeeklyChart();

let searchButton = document.getElementById("searchBtn");
let isSearchButtonClicked = false;

searchButton.addEventListener("click", async function () {
    const query = document.getElementById("searchInput").value.trim();
    const wrongInput = document.getElementById("wrongInput");
    const container = document.getElementById("searchResults");

    if (isSearchButtonClicked) {
        container.style.display = "none";
        container.innerHTML = "";
        isSearchButtonClicked = false;
        wrongInput.style.display = "none";
        return;
    }

    const showError = (message) => {
        wrongInput.innerText = message;
        wrongInput.style.display = "block";
    };

    const hideError = () => {
        wrongInput.style.display = "none";
    };

    if (!query) {
        showError("Your search query is empty");
        return;
    }

    hideError();

    let results;
    try {
        const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
        results = await response.json();
    } catch (error) {
        console.error("Error fetching search results:", error);
        showError("Something went wrong while searching");
        return;
    }

    if (results.length === 0) {
        showError("Your search query is not found");
        return;
    }

    hideError();
    container.innerHTML = "";

    results.forEach((news) => {
        const div = document.createElement("div");
        div.classList.add("news-item");

        const regex = new RegExp(`(${query})`, "gi");
        const title = news.title.replace(regex, `<mark>$1</mark>`);
        const description = (news.description || "").replace(
            regex,
            `<mark>$1</mark>`
        );

        div.innerHTML = `
            <h3>${title}</h3>
            <p>${description}</p>
            <a href="${news.url}" target="_blank">Read more</a>
        `;
        container.appendChild(div);
    });

    container.style.display = "grid";
    isSearchButtonClicked = true;
});

async function sendChat() {
    const date = document.getElementById("chatDate").value;
    const category = document.getElementById("chatCategory").value;
    const input = document.getElementById("chatInput");
    const box = document.getElementById("chatBox");
    const msg = input.value.trim();

    if (!msg || !date) return;

    const loader = document.getElementById("responseLoader");
    loader.classList.add("loader-visible"); // показуємо анімацію

    box.insertAdjacentHTML("beforeend", `<p class="user-request"><b>🧍‍♂️ You:</b> ${msg}</p>`);
    input.value = "...";

    try {
        const res = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg, date: date, category: category }),
        });

        const data = await res.json();

        box.insertAdjacentHTML("beforeend", `<p class="user-request"><b>🤖 AI:</b> ${data.response}</p>`);
    } catch (err) {
        box.insertAdjacentHTML("beforeend", `<p class="user-request"><b>🤖 AI:</b> ❌ Error occurred</p>`);
        console.error(err);
    } finally {
        input.value = "";
        loader.classList.remove("loader-visible"); // ховаємо після завершення
    }
}


