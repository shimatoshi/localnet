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
import SiteBuilderScreen from './screens/SiteBuilderScreen'
import ManageScreen from './screens/ManageScreen'
import ImageSearchScreen from './screens/ImageSearchScreen'

export default function App() {
  const location = useLocation()
  const isBrowser = location.pathname === '/browser'

  return (
    <>
      <Routes>
        <Route path="/" element={<HomeScreen />} />
        <Route path="/search" element={<SearchScreen />} />
        <Route path="/image-search" element={<ImageSearchScreen />} />
        <Route path="/browser" element={<BrowserScreen />} />
        <Route path="/tabs" element={<TabsScreen />} />
        <Route path="/history" element={<HistoryScreen />} />
        <Route path="/bookmarks" element={<BookmarksScreen />} />
        <Route path="/datasets" element={<DatasetsScreen />} />
        <Route path="/crawl" element={<CrawlScreen />} />
        <Route path="/site-builder" element={<SiteBuilderScreen />} />
        <Route path="/manage" element={<ManageScreen />} />
      </Routes>
      {!isBrowser && <BottomNav />}
    </>
  )
}
