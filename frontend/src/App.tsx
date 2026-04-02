import { Routes, Route, useLocation } from 'react-router-dom'
import BottomNav from './components/BottomNav'
import HomeScreen from './screens/HomeScreen'
import SearchScreen from './screens/SearchScreen'
import BrowserScreen from './screens/BrowserScreen'
import TabsScreen from './screens/TabsScreen'
import HistoryScreen from './screens/HistoryScreen'
import BookmarksScreen from './screens/BookmarksScreen'
import DatasetsScreen from './screens/DatasetsScreen'
import CrawlScreen from './screens/CrawlScreen'

export default function App() {
  const location = useLocation()
  const isBrowser = location.pathname === '/browser'

  return (
    <>
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route path="/search" element={<SearchScreen />} />
        <Route path="/browser" element={<BrowserScreen />} />
        <Route path="/tabs" element={<TabsScreen />} />
        <Route path="/history" element={<HistoryScreen />} />
        <Route path="/bookmarks" element={<BookmarksScreen />} />
        <Route path="/datasets" element={<DatasetsScreen />} />
        <Route path="/crawl" element={<CrawlScreen />} />
      </Routes>
      {!isBrowser && <BottomNav />}
    </>
  )
}
