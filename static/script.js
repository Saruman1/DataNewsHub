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
                    borderColor: "purple",
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
                    backgroundColor: "purple",
                },
            ],
        },
        options: { responsive: true },
    });
}

document
    .getElementById("filterBtn")
    .addEventListener("click", async function () {
        const category = document.getElementById("categoryFilter").value;
        const date = document.getElementById("chartDate").value;
        if (!category || !date) {
            alert("Оберіть і категорію, і дату!");
            return;
        }
        const newsData = await fetchData(
            `/news-by-category-and-date?category=${category}&date=${date}`
        );
        const newsContainer = document.getElementById("newsContainer");
        newsContainer.innerHTML = "";

        if (newsData.length === 0) {
            newsContainer.innerHTML = "<p>Новини відсутні</p>";
            newsContainer.style.display = "block";
            return;
        }

        newsData.forEach((news) => {
            const div = document.createElement("div");
            div.classList.add("news-item");
            div.innerHTML = `<h3>${news.title}</h3><p>${news.description}</p><a href="${news.url}" target="_blank">Read more</a>`;
            newsContainer.appendChild(div);
        });
        newsContainer.style.display = "grid";
    });

async function loadNewsByDate(date) {
    const newsContainer = document.getElementById("newsContainer");
    newsContainer.innerHTML = "";
    const newsData = await fetchData(`/news-by-date?date=${date}`);

    if (newsData.length === 0) {
        newsContainer.innerHTML = "<p>Новини відсутні</p>";
        return;
    }

    newsData.forEach((news) => {
        const div = document.createElement("div");
        div.classList.add("news-item");
        div.innerHTML = `<h3>${news.title}</h3><p>${news.description}</p><a href="${news.url}" target="_blank">Читати більше</a>`;
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
        const response = await fetch("/send-report", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: `date=${date}&email=${email}`,
        });
        const result = await response.json();
        document.getElementById("status").innerText = result.message;
    });

// Рендеримо графіки при завантаженні сторінки
renderWeeklyChart();
