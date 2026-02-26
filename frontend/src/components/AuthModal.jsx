function cls(...values) {
  return values.filter(Boolean).join(" ");
}

export default function AuthModal({
  authMode,
  onOpenAuth,
  onClose,
  onSignInSubmit,
  onSignUpSubmit,
  signInIdentity,
  onSignInIdentityChange,
  signUpHandle,
  onSignUpHandleChange,
  signUpEmail,
  onSignUpEmailChange,
  authFeedback,
  isAuthSubmitting,
  signUpHandlePlaceholder = "yourhandle",
  signUpEmailPlaceholder = "you@example.com",
  overlayClassName = "z-50",
}) {
  if (!authMode) {
    return null;
  }

  return (
    <div
      className={cls("fixed inset-0 flex items-center justify-center bg-[#111827]/60 p-4", overlayClassName)}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
        <div className="border-b border-[#e5e7eb] bg-[#f9fafb] p-3">
          <div className="grid grid-cols-2 gap-2 rounded-sm-ds bg-white p-1">
            <button
              type="button"
              onClick={() => onOpenAuth("signIn")}
              className={cls(
                "rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide",
                authMode === "signIn" ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]",
              )}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => onOpenAuth("signUp")}
              className={cls(
                "rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide",
                authMode === "signUp" ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]",
              )}
            >
              Sign Up
            </button>
          </div>
        </div>

        <div className="flex min-h-[374px] flex-col">
          {authMode === "signIn" ? (
            <form className="flex flex-1 flex-col" onSubmit={onSignInSubmit}>
              <div className="flex-1 space-y-4 p-6">
                <h3 className="text-lg font-bold text-[#111827]">Welcome back</h3>
                <p className="text-sm text-[#6b7280]">Use your email or handle to continue.</p>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                    Email or Handle
                  </label>
                  <input
                    type="text"
                    value={signInIdentity}
                    onChange={onSignInIdentityChange}
                    className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                    autoFocus
                  />
                </div>
                {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
              </div>
              <div className="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isAuthSubmitting}
                  className="rounded-sm-ds bg-[#06B6D4] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-cyan-600 disabled:opacity-50"
                >
                  Continue
                </button>
              </div>
            </form>
          ) : (
            <form className="flex flex-1 flex-col" onSubmit={onSignUpSubmit}>
              <div className="flex-1 space-y-4 p-6">
                <h3 className="text-lg font-bold text-[#111827]">Create your account</h3>
                <p className="text-sm text-[#6b7280]">Set a public handle, then publish your first board.</p>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                    Handle
                  </label>
                  <input
                    type="text"
                    value={signUpHandle}
                    onChange={onSignUpHandleChange}
                    className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                    placeholder={signUpHandlePlaceholder}
                    autoFocus
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                    Email
                  </label>
                  <input
                    type="email"
                    value={signUpEmail}
                    onChange={onSignUpEmailChange}
                    className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                    placeholder={signUpEmailPlaceholder}
                  />
                </div>
                {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
              </div>
              <div className="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isAuthSubmitting}
                  className="rounded-sm-ds bg-[#111827] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-black disabled:opacity-50"
                >
                  Create Account
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
