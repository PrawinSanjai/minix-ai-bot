import { useApp } from './context/AppContext'
import AnimatedBackground from './components/UI/AnimatedBackground'
import Login from './components/Auth/Login'
import Signup from './components/Auth/Signup'
import Onboarding from './components/Onboarding/Onboarding'
import Chat from './components/Chat/Chat'
import Settings from './components/Settings/Settings'
import './App.css'

const SCREENS = {
  login: Login,
  signup: Signup,
  onboarding: Onboarding,
  chat: Chat,
  settings: Settings,
}

export default function App() {
  const { state } = useApp()
  const ScreenComponent = SCREENS[state.currentScreen]

  return (
    <>
      <AnimatedBackground />
      <div id="app-container">
        <ScreenComponent />
      </div>
    </>
  )
}
