import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import type { User, OrganizationWithRole } from '../types/auth'
import {
  loginUser,
  registerUser,
  getMe,
  refreshTokens,
  logoutUser,
  AuthApiError,
} from '../services/auth'
import { listUserOrganizations } from '../services/organizations'

interface AuthContextType {
  user: User | null
  token: string | null
  organizations: OrganizationWithRole[]
  activeOrg: OrganizationWithRole | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => Promise<void>
  selectOrganization: (orgId: string) => void
  refreshOrganizations: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const ACCESS_TOKEN_KEY = 'corbel_access_token'
const REFRESH_TOKEN_KEY = 'corbel_refresh_token'
const ACTIVE_ORG_KEY = 'corbel_active_org_id'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [organizations, setOrganizations] = useState<OrganizationWithRole[]>([])
  const [activeOrg, setActiveOrg] = useState<OrganizationWithRole | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  const loadOrganizations = useCallback(
    async (accessToken: string, preferredOrgId?: string | null) => {
      try {
        const orgs = await listUserOrganizations(accessToken)
        setOrganizations(orgs)

        if (orgs.length > 0) {
          const storedOrgId = preferredOrgId || localStorage.getItem(ACTIVE_ORG_KEY)
          const matched = orgs.find((o) => o.id === storedOrgId)
          const selected = matched || orgs[0]
          setActiveOrg(selected)
          localStorage.setItem(ACTIVE_ORG_KEY, selected.id)
        } else {
          setActiveOrg(null)
          localStorage.removeItem(ACTIVE_ORG_KEY)
        }
      } catch (err) {
        console.error('Failed to load user organizations:', err)
      }
    },
    []
  )

  // Listen for session expiration events dispatched by apiClient
  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null)
      setToken(null)
      setOrganizations([])
      setActiveOrg(null)
    }
    window.addEventListener('corbel:session-expired', handleSessionExpired)
    return () => window.removeEventListener('corbel:session-expired', handleSessionExpired)
  }, [])

  // Initialize auth state on mount
  useEffect(() => {
    async function initAuth() {
      const storedAccessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
      const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)

      if (!storedAccessToken) {
        setIsLoading(false)
        return
      }

      try {
        const me = await getMe(storedAccessToken)
        setUser(me)
        setToken(storedAccessToken)
        await loadOrganizations(storedAccessToken)
      } catch (err) {
        if (err instanceof AuthApiError && err.code === 'INVALID_CREDENTIALS' && storedRefreshToken) {
          try {
            const tokens = await refreshTokens(storedRefreshToken)
            localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
            localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
            setToken(tokens.access_token)
            const me = await getMe(tokens.access_token)
            setUser(me)
            await loadOrganizations(tokens.access_token)
          } catch {
            localStorage.removeItem(ACCESS_TOKEN_KEY)
            localStorage.removeItem(REFRESH_TOKEN_KEY)
          }
        } else {
          localStorage.removeItem(ACCESS_TOKEN_KEY)
          localStorage.removeItem(REFRESH_TOKEN_KEY)
        }
      } finally {
        setIsLoading(false)
      }
    }

    initAuth()
  }, [loadOrganizations])

  const login = async (email: string, password: string): Promise<void> => {
    const tokens = await loginUser(email, password)
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
    setToken(tokens.access_token)

    const me = await getMe(tokens.access_token)
    setUser(me)
    await loadOrganizations(tokens.access_token)
  }

  const register = async (email: string, password: string, fullName: string): Promise<void> => {
    await registerUser(email, password, fullName)
    await login(email, password)
  }

  const logout = async (): Promise<void> => {
    if (token) {
      await logoutUser(token)
    }
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(ACTIVE_ORG_KEY)
    setUser(null)
    setToken(null)
    setOrganizations([])
    setActiveOrg(null)
  }

  const selectOrganization = (orgId: string): void => {
    const found = organizations.find((o) => o.id === orgId)
    if (found) {
      setActiveOrg(found)
      localStorage.setItem(ACTIVE_ORG_KEY, found.id)
    }
  }

  const refreshOrganizations = async (): Promise<void> => {
    if (token) {
      await loadOrganizations(token, activeOrg?.id)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        organizations,
        activeOrg,
        isLoading,
        login,
        register,
        logout,
        selectOrganization,
        refreshOrganizations,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
