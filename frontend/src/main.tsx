import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { limparCacheApi } from './utils/limparCacheApi';

// Apaga o cache de API deixado por versões antigas do service worker.
void limparCacheApi();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
