import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Chart, registerables } from 'chart.js';
import { ApiService, errorMessage } from '../../../core/api.service';
import { QuarterlyReport } from '../../../core/models';

Chart.register(...registerables);
const PALETTE = ['#2f5bea', '#12a37f', '#e8833a', '#9b51e0', '#d64570', '#2bb0d6'];

@Component({
  selector: 'app-admin-reports',
  imports: [FormsModule, CurrencyPipe, DecimalPipe],
  templateUrl: './admin-reports.component.html',
  styleUrl: './admin-reports.component.scss',
})
export class AdminReportsComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);
  report = signal<QuarterlyReport | null>(null);
  error = signal('');
  downloading = signal(false);
  now = new Date();
  year = this.now.getFullYear();
  quarter = Math.floor(this.now.getMonth() / 3) + 1;
  years = [this.year, this.year - 1, this.year - 2];

  outletCanvas = viewChild<ElementRef<HTMLCanvasElement>>('outletChart');
  monthCanvas = viewChild<ElementRef<HTMLCanvasElement>>('monthChart');
  categoryCanvas = viewChild<ElementRef<HTMLCanvasElement>>('categoryChart');
  private charts: Chart[] = [];

  ngOnInit() { this.load(); }
  ngOnDestroy() { this.charts.forEach(c => c.destroy()); }

  load() {
    this.api.getQuarterly(this.year, this.quarter).subscribe({
      next: r => { this.report.set(r); this.error.set(''); setTimeout(() => this.draw(r)); },
      error: e => this.error.set(errorMessage(e)),
    });
  }

  private draw(r: QuarterlyReport) {
    this.charts.forEach(c => c.destroy());
    this.charts = [];
    const money = (v: number | string) => '₹' + Number(v).toLocaleString('en-IN');
    const o = this.outletCanvas()?.nativeElement, m = this.monthCanvas()?.nativeElement, c = this.categoryCanvas()?.nativeElement;
    if (o) this.charts.push(new Chart(o, {
      type: 'bar',
      data: { labels: r.by_outlet.map(x => x.outlet), datasets: [{ label: 'Revenue', data: r.by_outlet.map(x => x.revenue), backgroundColor: PALETTE[0], borderRadius: 6 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { callback: money } } } },
    }));
    if (m) this.charts.push(new Chart(m, {
      type: 'line',
      data: { labels: r.monthly.map(x => x.month), datasets: [{ label: 'Revenue', data: r.monthly.map(x => x.revenue), borderColor: PALETTE[1], backgroundColor: PALETTE[1], tension: .3 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: money } } } },
    }));
    if (c) this.charts.push(new Chart(c, {
      type: 'doughnut',
      data: { labels: r.by_category.map(x => x.category), datasets: [{ data: r.by_category.map(x => x.revenue), backgroundColor: PALETTE }] },
      options: { plugins: { legend: { position: 'bottom' } } },
    }));
  }

  download(format: 'csv' | 'xlsx') {
    this.downloading.set(true);
    this.api.exportQuarterly(this.year, this.quarter, format).subscribe({
      next: blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `inventory_report_${this.year}_Q${this.quarter}.${format}`;
        a.click();
        URL.revokeObjectURL(a.href);
        this.downloading.set(false);
      },
      error: e => { this.error.set(errorMessage(e)); this.downloading.set(false); },
    });
  }
}
