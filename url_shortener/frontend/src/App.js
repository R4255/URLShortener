import React,{useState,useEffect} from "react";
import axios from 'axios'
import {toast,ToastContainer} from 'react-toastify'
import './App.css';
import { BrowserRouter as Router, Routes, Route , Link } from "react-router-dom";
import StatsPage from "./StatsPage";
//API Base URL - configurable for different environments
const API_BASE_URL=process.env.REACT_APP_API_BASE_URL || 'http://localhost:5000'
function AppContent(){
  const [url,seturl]=useState('')
  const [shortUrl,setshortUrl]=useState('')
  const [customCode,setCustomCode]=useState('')
  const [history,setHistory]=useState([])
  const [loading,setLoading]=useState(false)
  const [page,setPage]=useState(1)
  const [totalPages,setTotalPages]=useState(1)
  const [pages,setPages]=useState(1)
  const [copied,setCopied]=useState(false)
  //Load the URL history on component mounts
  useEffect(()=>{
    fetchUrlHistory(page)
  },[page])

  //Fetch the URL History from the API
  const fetchUrlHistory = async(pageNum) => {
    try{
      setLoading(true)
      const response = await axios.get(`${API_BASE_URL}/api/urls?page=${pageNum}&per_page=5`)
      setHistory(response?.data?.urls)
      setTotalPages(response?.data?.totalPages)
      setLoading(false)
    } catch (error){
      console.error('Error Fetching the URL History',error)
      toast.error('Error Fetching the URL History')
      setLoading(false)
    }
  }

  //Handling the URL Shortening Now
  const shortenUrl = async(e)=>{
    e.preventDefault()
    if (!url){
      toast.error('Please Enter the URl ')
      return 
    }
    try {
      setLoading(true)
      const payload = {url}
      if (customCode){
        payload.custom_code=customCode
      }
      const response = await axios.post(`${API_BASE_URL}/api/shorten`, payload)
      setshortUrl(response?.data?.short_url)
      seturl('')
      setCustomCode('')
      setLoading(false)
      //and also we will refresh the URL History 
      fetchUrlHistory(1)
      setPage(1)
      toast.success('URL Shortened Successfully')
    } catch(error) {
      console.error('Error Shortening the URL',error)
      if (error.response && error.response.data.error){
        toast.error(error.response.data.error)
      }else{
        toast.error('Failed to Shorten the URL')
      }
    }
  }
  
  // Now we will Copy the URL to the Clipboard
  const copyToClipboard=(text)=>{
    navigator.clipboard.writeText(text)
    .then(()=>{
      setCopied(true)
      toast.info('Copied to Clipboard')
      setTimeout(()=>setCopied(false),2000) //reset the copied state to false after 2sec to remove the visual indicator
    })
    .catch((error)=>{
      console.error('Error Copying to Clipboard',error)
      toast.error('Failed to Copy to Clipboard')
    })
  }

  //Now we will delete the Shortened URL
  const deleteURL = async(shortCode) => {
    if (window.confirm('Are u Sure u Want to Delete this URL ?')){
      try{
        await axios.delete(`${API_BASE_URL}/api/urls/${shortCode}`)
        toast.success('URL Deleted Successfully')
        fetchUrlHistory(page)
      } catch(error) {
        console.error('Error Deleting the URL', error)
        toast.error('Failed to Delete the URL')
      }
    }
  }

  //Now to view the URL Stats
  const viewStats = (shortCode) => {
    window.open(`/stats/${shortCode}`, '_blank');
  }

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900">
      <ToastContainer position="top-right" autoClose={3000} />
      
      <header className="bg-blue-600 text-white shadow-lg">
        <div className="container mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold">URL Shortener</h1>
          <p className="mt-2">Shorten, share, and track your links with ease</p>
        </div>
      </header>
      
      <main className="container mx-auto px-4 py-8">
        <section className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-2xl font-semibold mb-4">Create Short URL</h2>
          
          <form onSubmit={shortenUrl} className="space-y-4">
            <div>
              <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
                Enter Long URL
              </label>
              <input
                type="text"
                id="url"
                value={url}
                onChange={(e) => seturl(e.target.value)}
                placeholder="https://example.com/very/long/url/that/needs/shortening"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring focus:ring-blue-200"
                required
              />
            </div>
            
            <div>
              <label htmlFor="customCode" className="block text-sm font-medium text-gray-700 mb-1">
                Custom Code (Optional)
              </label>
              <input
                type="text"
                id="customCode"
                value={customCode}
                onChange={(e) => setCustomCode(e.target.value)}
                placeholder="e.g., mylink"
                className="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring focus:ring-blue-200"
              />
              <p className="text-xs text-gray-500 mt-1">
                Leave blank to generate a random code
              </p>
            </div>
            
            <button
              type="submit"
              className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring focus:ring-blue-200 disabled:opacity-50"
              disabled={loading}
            >
              {loading ? 'Shortening...' : 'Shorten URL'}
            </button>
          </form>
          
          {shortUrl && (
            <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
              <h3 className="font-semibold text-blue-800 mb-2">Your Short URL:</h3>
              <div className="flex items-center">
                <input
                  type="text"
                  value={shortUrl}
                  readOnly
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-l-md focus:outline-none"
                />
                <button
                  onClick={() => copyToClipboard(shortUrl)}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-r-md hover:bg-gray-300 focus:outline-none"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </section>
        
        <section className="bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-semibold mb-4">Your URLs</h2>
          
          {loading ? (
            <div className="text-center py-4">Loading...</div>
          ) : history.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Original URL
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Short URL
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Clicks
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {history.map((item) => (
                    <tr key={item.id}>
                      <td className="px-6 py-4 whitespace-nowrap truncate max-w-xs">
                        <a
                          href={item.original_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800"
                        >
                          {item.original_url}
                        </a>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-2">
                          <a
                            href={item.short_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-800"
                          >
                            {item.short_url}
                          </a>
                          <button
                            onClick={() => copyToClipboard(item.short_url)}
                            className="text-gray-500 hover:text-gray-700"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                          </button>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {item.clicks}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {new Date(item.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex space-x-2">
                          <button
                            onClick={() => viewStats(item.short_code)}
                            className="text-indigo-600 hover:text-indigo-800"
                          >
                            Stats
                          </button>
                          <button
                            onClick={() => deleteURL(item.short_code)}
                            className="text-red-600 hover:text-red-800"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              
              {totalPages > 1 && (
                <div className="flex justify-center mt-4 space-x-2">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page === 1}
                    className="px-3 py-1 border rounded-md disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="px-3 py-1">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1 border rounded-md disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-4 text-gray-500">
              No URLs shortened yet. Create your first short URL above!
            </div>
          )}
        </section>
      </main>
      
      <footer className="bg-gray-800 text-white mt-8">
        <div className="container mx-auto px-4 py-6">
          <p className="text-center">
            &copy; {new Date().getFullYear()} URL Shortener. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
function App(){
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AppContent/>}/>
        <Route path="/stats/:shortCode" element={<StatsPage/>}/>
      </Routes>
    </Router>
  )
}
export default App;