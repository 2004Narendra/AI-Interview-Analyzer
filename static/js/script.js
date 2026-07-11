// Placeholder JS for AI Interview Analyser
document.addEventListener('DOMContentLoaded', function () {
  // Theme initialization
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
  } catch (e) {}

  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.addEventListener('click', function(){
    const current = document.documentElement.getAttribute('data-theme');
    if (current === 'dark'){
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('theme', 'light');
      const icon = document.getElementById('theme-icon'); if(icon) icon.className = 'bi bi-moon-fill';
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('theme', 'dark');
      const icon = document.getElementById('theme-icon'); if(icon) icon.className = 'bi bi-sun-fill';
    }
  });

  fetch('/api/dashboard-data')
    .then(r => r.json())
    .then(data => {
      const stats = data.dashboard_stats || {};
      const charts = data.chart_data || {};
      document.getElementById('overall-score').textContent = stats.overall_score ?? '-';
      document.getElementById('total-interviews').textContent = stats.total_interviews_completed ?? '-';
      document.getElementById('average-score').textContent = stats.average_score ?? '-';
      const progress = stats.progress_percentage ?? 0;
      const bar = document.getElementById('progress-bar');
      bar.style.width = progress + '%';
      bar.setAttribute('aria-valuenow', progress);

      // Skill breakdown
      const list = document.getElementById('skill-breakdown');
      list.innerHTML = '';
      (stats.skill_breakdown || []).forEach(s => {
        const li = document.createElement('li');
        li.className = 'list-group-item d-flex justify-content-between align-items-center';
        li.textContent = s.name;
        const span = document.createElement('span');
        span.className = 'badge bg-primary rounded-pill';
        span.textContent = s.score;
        li.appendChild(span);
        list.appendChild(li);
      });

      // Score chart
      const scoreCtx = document.getElementById('scoreChart').getContext('2d');
      const scorePoints = (charts.score_points || []).map(p => p.score);
      const scoreLabels = (charts.score_points || []).map(p => p.label);
      new Chart(scoreCtx, {
        type: 'line',
        data: {
          labels: scoreLabels,
          datasets: [{ label: 'Score', data: scorePoints, borderColor: 'rgb(75, 192, 192)', tension: 0.3 }]
        },
        options: { responsive: true }
      });

      // Weakness chart
      const weakCtx = document.getElementById('weaknessChart').getContext('2d');
      const weaknessLabels = (charts.weakness_summary || []).map(w => w.label);
      const weaknessCounts = (charts.weakness_summary || []).map(w => w.count);
      new Chart(weakCtx, {
        type: 'bar',
        data: {
          labels: weaknessLabels,
          datasets: [{ label: 'Count', data: weaknessCounts, backgroundColor: 'rgba(255,99,132,0.6)' }]
        },
        options: { responsive: true }
      });
    })
    .catch(() => {
      // ignore errors for now
    });
});
