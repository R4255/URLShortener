// StatsPage.js
import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import { Chart, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend } from 'chart.js';
import { ToastContainer, toast } from 'react-toastify';

// Register Chart.js components
Chart.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

// API base URL - configurable for different environments
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5000';

function StatsPage() {
  const { shortCode } = useParams();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const response = await axios.get(`${API_BASE_URL}/api/stats/${shortCode}`);
        setStats(response.data);
        setError(null);
      } catch (err) {
        console.error('Error fetching stats:', err);
        setError('Failed to load statistics. The URL may not exist or has been deleted.');
        toast.error('Failed to load statistics');
      } finally {
        setLoading(false);
      }
    };
    
    fetchStats();
  }, [shortCode]);
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-xl">Loading statistics...</div>
      </div>
    );
  }
  
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="bg-white p-8 rounded-lg shadow-md max-w-md">
          <h1 className="text-2xl font-bold text-red-600 mb-4">Error</h1>
          <p className="text-gray-700">{error}</p>
          <button 
            onClick={() => window.history.back()} 
            className="mt-6 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Go Back
          </button>
        </div>
      </div>
    );
  }
  
  if (!stats) {
    return null;
  }
  
  // Prepare chart data
  const chartData = {
    labels: stats.daily_stats.map(day => day.date),
    datasets: [
      {
        label: 'Daily Clicks',
        data: stats.daily_stats.map(day => day.clicks),
        fill: false,
        backgroundColor: 'rgba(59, 130, 246, 0.5)',
        borderColor: 'rgba(59, 130, 246, 1)',
        tension: 0.1
      }
    ]
  };
  
  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'Daily Clicks (Last 30 Days)'
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Number of Clicks'
        },
        ticks: {
          precision: 0
        }
      },
      x: {
        title: {
          display: true,
          text: 'Date'
        }
      }
    }
  };
  
  return (
    <div className="min-h-screen bg-gray-100">
      <ToastContainer position="top-right" autoClose={3000} />
      
      <header className="bg-blue-600 text-white shadow-lg">
        <div className="container mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold">URL Analytics</h1>
          <p className="mt-2">Detailed statistics for your shortened URL</p>
        </div>
      </header>
      
      <main className="container mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-semibold mb-4">URL Details</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-lg font-medium mb-2">Original URL</h3>
              <a 
                href={stats.original_url} 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-blue-600 hover:text-blue-800 break-all"
              >
                {stats.original_url}
              </a>
            </div>
            
            <div>
              <h3 className="text-lg font-medium mb-2">Short URL</h3>
              <div className="flex items-center">
                <a 
                  href={stats.short_url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="text-blue-600 hover:text-blue-800 mr-2"
                >
                  {stats.short_url}
                </a>
                <button 
                  onClick={() => {
                    navigator.clipboard.writeText(stats.short_url);
                    toast.info('Copied to clipboard!');
                  }}
                  className="text-gray-500 hover:text-gray-700"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              </div>
            </div>
            
            <div>
              <h3 className="text-lg font-medium mb-2">Created On</h3>
              <p>{new Date(stats.created_at).toLocaleString()}</p>
            </div>
            
            <div>
              <h3 className="text-lg font-medium mb-2">Total Clicks</h3>
              <p className="text-2xl font-bold text-blue-600">{stats.total_clicks}</p>
            </div>
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-semibold mb-4">Click Analytics</h2>
          
          <div className="h-64 md:h-96">
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>
        
        <div className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-semibold mb-4">Recent Activity</h2>
          
          {stats.recent_access.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Date & Time
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      IP Address
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Referrer
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      User Agent
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {stats.recent_access.map((access, index) => (
                    <tr key={index}>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {new Date(access.accessed_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {access.ip_address || 'Unknown'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap truncate max-w-xs">
                        {access.referrer || 'Direct'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap truncate max-w-xs">
                        {access.user_agent || 'Unknown'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-4 text-gray-500">
              No recent activity to display.
            </div>
          )}
        </div>
      </main>
      
      <footer className="bg-gray-800 text-white mt-8">
        <div className="container mx-auto px-4 py-6">
          <p className="text-center">
            &copy; {new Date().getFullYear()} URL Shortener. All rights reserved.
          </p>
          <p className="text-center mt-2">
            <button 
              onClick={() => window.history.back()} 
              className="text-blue-300 hover:text-blue-100"
            >
              ← Back to Dashboard
            </button>
          </p>
        </div>
      </footer>
    </div>
  );
}

export default StatsPage;