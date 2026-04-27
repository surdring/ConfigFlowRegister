import { useState, useEffect, useCallback, useMemo, memo } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import { readTextFile } from '@tauri-apps/plugin-fs';
import { writeText } from '@tauri-apps/plugin-clipboard-manager';
import { Virtuoso } from 'react-virtuoso';
import toast, { Toaster } from 'react-hot-toast';
import type { Account, PoolStats, ResetInfo, TakeAccountResult, ImportResult, PageResult, SwitchAccountResult } from './types';

// 虚拟列表行高
const ROW_HEIGHT = 32;

// 表格行组件 - memo 防止不必要的重渲染
interface RowData {
  accounts: Account[];
  selectedEmails: Set<string>;
  toggleSelect: (email: string) => void;
  formatDate: (date: string | null) => string;
  onSwitchAccount: (email: string) => void;
  switchingEmail: string | null;
}

const TableRow = memo(({ index, data }: { index: number; data: RowData }) => {
  const { accounts, selectedEmails, toggleSelect, formatDate, onSwitchAccount, switchingEmail } = data;
  const account = accounts[index];
  if (!account) return null;
  const isEven = index % 2 === 0;
  const isSwitching = switchingEmail === account.email;

  return (
    <div className={`flex h-8 border-b border-gray-100 hover:bg-[#5A4A8D]/5 transition-colors ${isEven ? 'bg-white' : 'bg-gray-50'}`}>
      <div className="px-2 w-10 flex items-center justify-center flex-shrink-0">
        <input
          type="checkbox"
          checked={selectedEmails.has(account.email)}
          onChange={() => toggleSelect(account.email)}
          className="rounded border-gray-300 h-3 w-3"
        />
      </div>
      <div className="px-2 w-[32%] text-xs font-medium text-gray-900 truncate flex items-center min-w-0">{account.email}</div>
      <div className="px-2 w-[10%] flex items-center justify-center flex-shrink-0">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
          account.weekly_exhausted ? 'bg-[#E05656]/10 text-[#E05656]' :
          account.daily_exhausted ? 'bg-[#E6A23C]/10 text-[#E6A23C]' :
          'bg-[#20B2AA]/10 text-[#0F766E]'
        }`}>
          {account.weekly_exhausted ? '周耗尽' :
           account.daily_exhausted ? '日耗尽' : '可用'}
        </span>
      </div>
      <div className="px-2 w-[10%] text-xs text-gray-600 flex items-center justify-center flex-shrink-0">
        {account.daily_exhausted ? '✗' : '✓'}
      </div>
      <div className="px-2 w-[10%] text-xs text-gray-600 flex items-center justify-center flex-shrink-0">
        {account.weekly_exhausted ? '✗' : '✓'}
      </div>
      <div className="px-2 w-[10%] text-xs text-gray-600 flex items-center justify-center flex-shrink-0">{account.total_uses}</div>
      <div className="px-2 w-[12%] text-xs text-gray-600 flex items-center justify-center flex-shrink-0">{formatDate(account.last_used_at)}</div>
      <div className="px-2 w-[16%] flex items-center justify-center flex-shrink-0">
        <button
          onClick={() => onSwitchAccount(account.email)}
          disabled={isSwitching}
          className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
            isSwitching 
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-[#5A4A8D]/10 text-[#5A4A8D] hover:bg-[#5A4A8D]/20 active:bg-[#5A4A8D]/30'
          }`}
        >
          {isSwitching ? '登录中...' : '一键登录'}
        </button>
      </div>
    </div>
  );
});

function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState<PoolStats | null>(null);
  const [resetInfo, setResetInfo] = useState<ResetInfo | null>(null);
  const [selectedEmails, setSelectedEmails] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [switchingEmail, setSwitchingEmail] = useState<string | null>(null);
  const [currentAccount, setCurrentAccount] = useState<string | null>(null);

  // 分页计算
  const totalPages = useMemo(() => Math.ceil(totalCount / pageSize), [totalCount, pageSize]);
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalCount);

  // 服务端分页加载（带搜索/过滤）
  const loadData = useCallback(async () => {
    try {
      const [pageData, statsData, resetData, current] = await Promise.all([
        invoke<PageResult>('get_accounts_page', {
          page: currentPage,
          pageSize,
          search: search.trim() || null,
          statusFilter: statusFilter || null,
        }),
        invoke<PoolStats>('get_stats'),
        invoke<ResetInfo>('get_reset_info'),
        invoke<string | null>('get_current_account'),
      ]);
      setAccounts(pageData.accounts);
      setTotalCount(pageData.total);
      setStats(statsData);
      setResetInfo(resetData);
      setCurrentAccount(current);
    } catch (error) {
      toast.error('加载数据失败: ' + error);
    }
  }, [currentPage, pageSize, search, statusFilter]);

  // 加载数据
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // 搜索防抖：只重置页码，loadData 会自动执行
  useEffect(() => {
    const timer = setTimeout(() => {
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, statusFilter]);

  const handleTakeAccount = async () => {
    setIsLoading(true);
    try {
      const result = await invoke<TakeAccountResult>('take_account');
      if (result.email) {
        await writeText(result.email);
        toast.success(`已取用并复制: ${result.email}`);
      } else {
        toast.error(result.message || '没有可用账号');
      }
      await loadData();
    } catch (error) {
      toast.error('取用账号失败: ' + error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSwitchAccount = async (email: string) => {
    setSwitchingEmail(email);
    try {
      const result = await invoke<SwitchAccountResult>('switch_windsurf_account', {
        email,
        password: null,
      });
      if (result.success) {
        toast.success(result.message);
        setCurrentAccount(email);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      toast.error('一键登录失败: ' + error);
    } finally {
      setSwitchingEmail(null);
    }
  };

  const handleTakeAndSwitch = async () => {
    setIsLoading(true);
    try {
      const result = await invoke<SwitchAccountResult>('take_and_switch');
      if (result.success) {
        toast.success(result.message);
        setCurrentAccount(result.email);
      } else {
        toast.error(result.message);
      }
      await loadData();
    } catch (error) {
      toast.error('取用并登录失败: ' + error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBatchDelete = async () => {
    if (selectedEmails.size === 0) {
      toast.error('请先选择要删除的账号');
      return;
    }
    if (!confirm(`确定要删除选中的 ${selectedEmails.size} 个账号吗？`)) return;
    try {
      const count = await invoke<number>('batch_delete_accounts', { emails: Array.from(selectedEmails) });
      toast.success(`已删除 ${count} 个账号`);
      setSelectedEmails(new Set());
      await loadData();
    } catch (error) {
      toast.error('批量删除失败: ' + error);
    }
  };

  const handleCheckReset = async () => {
    try {
      await invoke('check_reset');
      toast.success('重置检查完成');
      await loadData();
    } catch (error) {
      toast.error('检查失败: ' + error);
    }
  };

  const handleImportFromFile = async () => {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: 'JSON', extensions: ['json'] }],
      });
      
      if (selected && typeof selected === 'string') {
        const content = await readTextFile(selected);
        const result = await invoke<ImportResult>('import_from_json', { jsonContent: content });
        toast.success(`导入完成: ${result.imported} 个成功, ${result.skipped} 个已存在`);
        if (result.errors.length > 0) {
          result.errors.forEach(err => toast.error(err));
        }
        await loadData();
      }
    } catch (error) {
      toast.error('导入失败: ' + error);
    }
  };

  const handleImportFromText = async () => {
    if (!importText.trim()) {
      toast.error('请输入邮箱列表');
      return;
    }
    
    const emails = importText
      .split('\n')
      .map(e => e.trim())
      .filter(e => e && e.includes('@'));
    
    if (emails.length === 0) {
      toast.error('未找到有效的邮箱');
      return;
    }
    
    try {
      const result = await invoke<ImportResult>('import_accounts', { emails });
      toast.success(`导入完成: ${result.imported} 个成功, ${result.skipped} 个已存在`);
      if (result.errors.length > 0) {
        result.errors.forEach(err => toast.error(err));
      }
      setImportText('');
      setShowImportModal(false);
      await loadData();
    } catch (error) {
      toast.error('导入失败: ' + error);
    }
  };

  const toggleSelectAll = () => {
    const currentPageEmails = accounts.map((a: Account) => a.email);
    const allSelected = currentPageEmails.every((email: string) => selectedEmails.has(email));
    
    if (allSelected) {
      // 取消当前页的选择
      setSelectedEmails(prev => {
        const newSet = new Set(prev);
        currentPageEmails.forEach((email: string) => newSet.delete(email));
        return newSet;
      });
    } else {
      // 选择当前页所有
      setSelectedEmails(prev => {
        const newSet = new Set(prev);
        currentPageEmails.forEach((email: string) => newSet.add(email));
        return newSet;
      });
    }
  };

  const toggleSelect = (email: string) => {
    setSelectedEmails(prev => {
      const newSet = new Set(prev);
      if (newSet.has(email)) {
        newSet.delete(email);
      } else {
        newSet.add(email);
      }
      return newSet;
    });
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Toaster position="top-right" />
      
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">账号池管理</h1>
            <div className="flex items-center gap-3">
              {currentAccount && (
                <span className="text-sm text-[#5A4A8D] font-medium bg-[#5A4A8D]/10 px-3 py-1 rounded-full">
                  当前登录: {currentAccount}
                </span>
              )}
              <span className="text-sm text-gray-500">策略: Round Robin</span>
              <button
                onClick={handleCheckReset}
                className="px-4 py-2 bg-[#5A4A8D] text-white rounded-lg hover:bg-[#6B5A9D] active:bg-[#4A3A7D] transition-colors"
              >
                检查重置
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="p-6 flex flex-col h-[calc(100vh-80px)] overflow-hidden">
        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div className="bg-white rounded-lg shadow-sm p-3 border-l-4 border-gray-400">
            <div className="text-xs text-gray-500 uppercase tracking-wider">总数</div>
            <div className="text-3xl font-bold text-gray-800">{stats?.total || 0}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3 border-l-4 border-[#20B2AA]">
            <div className="text-xs text-gray-500 uppercase tracking-wider">可用</div>
            <div className="text-3xl font-bold text-[#0D9488]">{stats?.available || 0}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3 border-l-4 border-[#E6A23C]">
            <div className="text-xs text-gray-500 uppercase tracking-wider">日耗尽</div>
            <div className={`text-3xl font-bold ${(stats?.daily_exhausted || 0) > 0 ? 'text-[#DC2626]' : 'text-[#D97706]'}`}>{stats?.daily_exhausted || 0}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3 border-l-4 border-[#E05656]">
            <div className="text-xs text-gray-500 uppercase tracking-wider">周耗尽</div>
            <div className={`text-3xl font-bold ${(stats?.weekly_exhausted || 0) > 0 ? 'text-[#DC2626]' : 'text-[#DC2626]/60'}`}>{stats?.weekly_exhausted || 0}</div>
          </div>
        </div>

        {/* Reset Info */}
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">下次日重置:</span>
              <span className="text-sm font-medium">
                {resetInfo?.next_daily_reset ? new Date(resetInfo.next_daily_reset).toLocaleString('zh-CN') : '-'}
              </span>
              <span className="text-xs text-[#5A4A8D]">({resetInfo?.daily_reset_in || '-'})</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">下次周重置:</span>
              <span className="text-sm font-medium">
                {resetInfo?.next_weekly_reset ? new Date(resetInfo.next_weekly_reset).toLocaleString('zh-CN') : '-'}
              </span>
              <span className="text-xs text-[#5A4A8D]">({resetInfo?.weekly_reset_in || '-'})</span>
            </div>
          </div>
        </div>

        {/* Actions + Table */}
        <div className="bg-white rounded-lg shadow-sm flex-1 overflow-hidden flex flex-col">
          <div className="p-3 border-b border-gray-200">
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={handleTakeAccount}
                disabled={isLoading}
                className="px-4 py-2 bg-[#5A4A8D] text-white rounded-lg hover:bg-[#6B5A9D] active:bg-[#4A3A7D] transition-colors disabled:opacity-50 disabled:bg-[#5A4A8D]/50 text-sm font-medium"
              >
                {isLoading ? '加载中...' : '取用账号'}
              </button>
              <button
                onClick={handleTakeAndSwitch}
                disabled={isLoading}
                className="px-4 py-2 bg-[#20B2AA] text-white rounded-lg hover:bg-[#0F766E] active:bg-[#0A5C57] transition-colors disabled:opacity-50 disabled:bg-[#20B2AA]/50 text-sm font-medium"
              >
                {isLoading ? '登录中...' : '一键登录'}
              </button>
              <button
                onClick={() => setShowImportModal(true)}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
              >
                导入账号
              </button>
              <button
                onClick={handleImportFromFile}
                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium"
              >
                从文件导入
              </button>
              <div className="w-px h-8 bg-gray-200 mx-1"></div>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索邮箱..."
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-48 focus:outline-none focus:ring-2 focus:ring-[#5A4A8D] focus:border-[#5A4A8D]"
              />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#5A4A8D] focus:border-[#5A4A8D]"
              >
                <option value="">全部状态</option>
                <option value="available">可用</option>
                <option value="daily_exhausted">日耗尽</option>
                <option value="weekly_exhausted">周耗尽</option>
              </select>
              <div className="flex-1"></div>
              {selectedEmails.size > 0 && (
                <>
                  <button
                    onClick={async () => {
                      try {
                        const count = await invoke<number>('batch_mark_daily_exhausted', { emails: Array.from(selectedEmails) });
                        toast.success(`已标记 ${count} 个日耗尽`);
                        setSelectedEmails(new Set());
                        await loadData();
                      } catch (error) { toast.error('操作失败: ' + error); }
                    }}
                    className="px-3 py-2 bg-[#E6A23C] text-white rounded-lg hover:bg-[#F0B050] active:bg-[#D09030] transition-colors text-sm"
                  >
                    标记日耗尽
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const count = await invoke<number>('batch_mark_weekly_exhausted', { emails: Array.from(selectedEmails) });
                        toast.success(`已标记 ${count} 个周耗尽`);
                        setSelectedEmails(new Set());
                        await loadData();
                      } catch (error) { toast.error('操作失败: ' + error); }
                    }}
                    className="px-3 py-2 bg-[#E05656] text-white rounded-lg hover:bg-[#F07070] active:bg-[#C04545] transition-colors text-sm"
                  >
                    标记周耗尽
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const count = await invoke<number>('batch_unmark_exhausted', { emails: Array.from(selectedEmails) });
                        toast.success(`已恢复 ${count} 个账号`);
                        setSelectedEmails(new Set());
                        await loadData();
                      } catch (error) { toast.error('操作失败: ' + error); }
                    }}
                    className="px-3 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors text-sm"
                  >
                    取消标记
                  </button>
                  <button
                    onClick={handleBatchDelete}
                    className="px-3 py-2 bg-[#E05656] text-white rounded-lg hover:bg-[#F07070] active:bg-[#C04545] transition-colors text-sm"
                  >
                    删除选中
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Table Header */}
          <div className="bg-[#F9FAFB] border-b border-gray-200 flex flex-shrink-0">
            <div className="px-2 py-2 w-10 flex items-center justify-center flex-shrink-0">
              <input
                type="checkbox"
                checked={accounts.length > 0 && accounts.every((a: Account) => selectedEmails.has(a.email))}
                onChange={toggleSelectAll}
                className="rounded border-gray-300"
              />
            </div>
            <div className="px-2 py-2 w-[32%] text-xs font-medium text-gray-700 flex items-center min-w-0">邮箱</div>
            <div className="px-2 py-2 w-[10%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">状态</div>
            <div className="px-2 py-2 w-[10%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">日配额</div>
            <div className="px-2 py-2 w-[10%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">周配额</div>
            <div className="px-2 py-2 w-[10%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">累计使用</div>
            <div className="px-2 py-2 w-[12%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">上次使用</div>
            <div className="px-2 py-2 w-[16%] text-xs font-medium text-gray-700 flex items-center justify-center flex-shrink-0">操作</div>
          </div>

          {/* Virtual List Body */}
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {accounts.length > 0 ? (
              <Virtuoso
                data={accounts}
                fixedItemHeight={ROW_HEIGHT}
                itemContent={(index) => (
                  <TableRow
                    index={index}
                    data={{
                      accounts,
                      selectedEmails,
                      toggleSelect,
                      formatDate,
                      onSwitchAccount: handleSwitchAccount,
                      switchingEmail,
                    }}
                  />
                )}
                style={{ height: '100%' }}
              />
            ) : (
              <div className="px-4 py-8 text-center text-gray-500">
                暂无账号，请先导入
              </div>
            )}
          </div>

          {/* 分页控件 */}
          {totalCount > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
              <div className="flex items-center gap-4">
                <span className="text-sm text-gray-700">
                  显示 {startIndex + 1}-{endIndex} 条，共 {totalCount} 条
                </span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="text-sm border border-gray-300 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-[#5A4A8D] focus:border-[#5A4A8D]"
                >
                  <option value={10}>10条/页</option>
                  <option value={20} selected>20条/页</option>
                  <option value={30}>30条/页</option>
                  <option value={50}>50条/页</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(1)}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  首页
                </button>
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  上一页
                </button>
                <span className="text-sm text-gray-700 px-2">
                  第 {currentPage} / {totalPages} 页
                </span>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  下一页
                </button>
                <button
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  末页
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-[500px] animate-fade-in">
            <h3 className="text-lg font-semibold mb-4">导入账号</h3>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder="请输入邮箱列表，每行一个"
              className="w-full h-48 px-3 py-2 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-[#5A4A8D] focus:border-[#5A4A8D]"
            />
            <div className="flex gap-3 mt-4">
              <button
                onClick={handleImportFromText}
                className="flex-1 px-4 py-2 bg-[#5A4A8D] text-white rounded-lg hover:bg-[#6B5A9D] active:bg-[#4A3A7D] transition-colors"
              >
                导入
              </button>
              <button
                onClick={() => setShowImportModal(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
