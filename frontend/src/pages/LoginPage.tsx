import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Invalid email or password";
      setError(typeof msg === "string" ? msg : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="login-surface grid min-h-dvh place-items-center p-4">
      <div className="grid w-full max-w-sm items-center overflow-hidden rounded-xl border bg-card shadow-lg md:max-w-3xl md:grid-cols-2">
        <aside className="hidden self-stretch border-r bg-muted/40 md:flex md:flex-col">
          <img src="/standards-binder.jpg" alt="" width="900" height="600" className="min-h-0 w-full flex-1 object-cover" />
          <div className="border-t-4 border-gold p-6">
            <h2 className="text-lg font-semibold">Standards library</h2>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              Find standard documents, review earlier editions, and track changes to the standards your team uses.
            </p>
          </div>
        </aside>
        <div className="space-y-4 p-6">
          <header className="space-y-1 text-center">
            <img src="/biorad-medisys.svg" alt="Biorad Medisys" className="mx-auto mb-4 h-auto w-60 max-w-full" />
            <h1 className="text-xl font-bold">Welcome back</h1>
            <p className="text-sm text-muted-foreground">Sign in to StandardSphere</p>
            <p className="text-sm text-muted-foreground md:hidden">Find standards, review editions, and track changes.</p>
          </header>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Error alert */}
            {error && (
              <div role="alert" className="rounded-lg border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {error}
              </div>
            )}

            {/* Email */}
            <div className="space-y-2">
              <Label htmlFor="email">Email address</Label>
              <div className="relative">
                <Input
                  id="email"
                  type="email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  autoFocus
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-10"
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" className="w-full gap-2" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                </>
              )}
            </Button>
          </form>

          <p className="text-center text-xs text-muted-foreground">
            Internal use only — authorized personnel only
          </p>
        </div>
      </div>
    </main>
  );
}
