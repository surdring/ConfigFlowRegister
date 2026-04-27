export interface Account {
  email: string;
  status: 'available' | 'exhausted';
  daily_exhausted: boolean;
  weekly_exhausted: boolean;
  last_used_at: string | null;
  total_uses: number;
  notes: string;
}

export interface PoolStats {
  total: number;
  available: number;
  daily_exhausted: number;
  weekly_exhausted: number;
}

export interface ResetInfo {
  next_daily_reset: string;
  next_weekly_reset: string;
  daily_reset_in: string;
  weekly_reset_in: string;
}

export interface TakeAccountResult {
  email: string;
  message: string;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface PageResult {
  accounts: Account[];
  total: number;
}

export interface SwitchAccountResult {
  email: string;
  message: string;
  success: boolean;
}
