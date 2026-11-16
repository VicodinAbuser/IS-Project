import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, errorMessage } from '../../../core/api.service';
import { AuthService } from '../../../core/auth.service';
import { Choice, PermissionInfo, ProfileCode, ProfileInfo, UPDATED_WITHIN, UserDetail, UserRow } from '../../../core/models';

/** Who is registered, which profiles they have, and what each profile may do (USERS, USER_PROFILES,
 *  PROFILES, AUTHORIZATIONS, PERMISSIONS tables). Changing access needs the USER_MANAGE permission. */
@Component({
  selector: 'app-admin-users',
  imports: [FormsModule, DatePipe, CurrencyPipe],
  templateUrl: './admin-users.component.html',
  styleUrl: './admin-users.component.scss',
})
export class AdminUsersComponent implements OnInit {
  private api = inject(ApiService);
  auth = inject(AuthService);
  tab = signal<'users' | 'matrix'>('users');
  users = signal<UserRow[]>([]);
  profiles = signal<ProfileInfo[]>([]);
  permissions = signal<PermissionInfo[]>([]);
  selected = signal<UserDetail | null>(null);
  editProfiles: Record<string, boolean> = {};
  error = signal('');
  message = signal('');
  loading = signal(false);

  filter = { search: '', profile: '', status: '', sort: 'updated_desc', updated_within_days: null as number | null, limit: 100 };
  sorts: Choice[] = [
    { value: 'updated_desc', label: 'Latest updated' }, { value: 'created_desc', label: 'Newest accounts' },
    { value: 'last_login_desc', label: 'Last login' }, { value: 'name_asc', label: 'Name A–Z' },
    { value: 'created_asc', label: 'Oldest accounts' },
  ];
  within = UPDATED_WITHIN;
  newStaff = { open: false, name: '', email: '', password: '', profiles: { STORE_MANAGER: true } as Record<string, boolean> };

  ngOnInit() {
    this.api.getProfiles().subscribe(p => this.profiles.set(p));
    this.api.getPermissions().subscribe(p => this.permissions.set(p));
    this.load();
  }

  load() {
    this.loading.set(true);
    this.api.getUsers(this.filter).subscribe({
      next: u => { this.users.set(u); this.loading.set(false); },
      error: e => { this.error.set(errorMessage(e)); this.loading.set(false); },
    });
  }

  open(u: UserRow) {
    this.api.getUser(u.id).subscribe(d => this.show(d));
  }

  private show(d: UserDetail) {
    this.selected.set(d);
    this.editProfiles = Object.fromEntries(this.profiles().map(p => [p.code, d.profiles.includes(p.code)]));
  }

  private done(d: UserDetail, text: string) {
    this.show(d);
    this.flash(text);
    this.load();
  }

  private flash(text: string) {
    this.error.set('');
    this.message.set(text);
    setTimeout(() => this.message.set(''), 2500);
  }

  saveProfiles() {
    const d = this.selected()!;
    const chosen = Object.entries(this.editProfiles).filter(([, on]) => on).map(([code]) => code as ProfileCode);
    this.api.setProfiles(d.id, chosen).subscribe({
      next: r => this.done(r, `Profiles of ${r.name} saved`), error: e => this.error.set(errorMessage(e)),
    });
  }

  toggleStatus() {
    const d = this.selected()!;
    const next = d.account_status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    if (next === 'DISABLED' && !confirm(`Disable ${d.name}? They will no longer be able to log in.`)) return;
    this.api.setStatus(d.id, next).subscribe({
      next: r => this.done(r, `${r.name} is now ${r.account_status.toLowerCase()}`), error: e => this.error.set(errorMessage(e)),
    });
  }

  unlock() {
    this.api.unlockUser(this.selected()!.id).subscribe({
      next: r => this.done(r, `${r.name} unlocked`), error: e => this.error.set(errorMessage(e)),
    });
  }

  createStaff() {
    const s = this.newStaff;
    const profiles = Object.entries(s.profiles).filter(([, on]) => on).map(([code]) => code as ProfileCode);
    this.api.createStaff({ name: s.name, email: s.email, password: s.password, profiles }).subscribe({
      next: r => {
        this.newStaff = { open: false, name: '', email: '', password: '', profiles: { STORE_MANAGER: true } };
        this.done(r, `Account created for ${r.name}`);
      },
      error: e => this.error.set(errorMessage(e)),
    });
  }

  isLocked(u: UserRow) { return !!u.locked_until && new Date(u.locked_until) > new Date(); }
  hasPermission(p: ProfileInfo, code: string) { return p.permissions.includes(code as any); }
  label(code: string) { return code.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); }
  staffProfiles() { return this.profiles().filter(p => p.is_staff); }
}
