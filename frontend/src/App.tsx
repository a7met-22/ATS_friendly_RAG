import React, { useState } from 'react';
import { Navbar } from './components/layout/Navbar';
import { AuthModal } from './components/layout/AuthModal';
import { DocumentsPanel } from './components/documents/DocumentsPanel';
import { ChatWorkspace } from './components/chat/ChatWorkspace';
import { AdminDashboard } from './components/admin/AdminDashboard';

export function App() {
  const [activeTab, setActiveTab] = useState<'workspace' | 'admin'>('workspace');
  const [authOpen, setAuthOpen] = useState(false);

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-slate-100 overflow-hidden">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenAuth={() => setAuthOpen(true)}
      />
      {activeTab === 'workspace' ? (
        <div className="flex-1 flex min-h-0">
          <DocumentsPanel />
          <ChatWorkspace />
        </div>
      ) : (
        <AdminDashboard />
      )}
      <AuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} />
    </div>
  );
}

export default App;
