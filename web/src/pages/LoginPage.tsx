import { ArrowRight, Check, LockKeyhole, MessageCircleMore, Phone, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiClientError } from "../services/apiClient";
import { requestOtp, verifyOtp } from "../services/authApi";

export function LoginPage() {
  const { session, completeLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [hint, setHint] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [countdown, setCountdown] = useState(0);

  useEffect(() => {
    if (session) navigate(session.family ? "/" : "/family", { replace: true });
  }, [navigate, session]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setInterval(() => setCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [countdown]);

  const sendCode = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入正确的 11 位手机号");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const challenge = await requestOtp(phone);
      setHint(challenge.delivery_hint ?? "验证码已发送");
      setCountdown(challenge.resend_after);
      setStep("code");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "验证码发送失败");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (step === "phone") return sendCode();
    if (!/^\d{6}$/.test(code)) {
      setError("请输入 6 位验证码");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const auth = await verifyOtp(phone, code);
      completeLogin(auth);
      const requestedPath = (location.state as { from?: string } | null)?.from;
      navigate(auth.family ? requestedPath || "/" : "/family", { replace: true });
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "登录失败，请重试");
    } finally {
      setBusy(false);
    }
  };

  return <main className="login-page">
    <section className="login-story">
      <div className="login-brand"><span className="brand-bean"><span /></span><strong>家庭故事豆</strong></div>
      <div className="login-copy"><span>PRIVATE FAMILY ARCHIVE</span><h1>家人的声音，<br />只属于家人。</h1><p>登录后继续收集日常里的笑声、金句和成长故事。</p></div>
      <div className="login-promise"><LockKeyhole size={17} /><span>默认私密 · 家庭隔离 · 随时删除</span></div>
    </section>

    <section className="login-form-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="login-card-icon">{step === "phone" ? <Phone /> : <MessageCircleMore />}</div>
        <span className="section-kicker">{step === "phone" ? "欢迎回来" : "验证手机号"}</span>
        <h2>{step === "phone" ? "打开家庭故事" : `验证码已发送至 ${phone.slice(0, 3)}****${phone.slice(-4)}`}</h2>
        <p>{step === "phone" ? "使用手机号登录，新用户会自动创建账号。" : "验证码五分钟内有效，验证成功后即刻失效。"}</p>

        {step === "phone" ? <label className="form-field"><span>手机号</span><div><span className="country-code">+86</span><input autoFocus inputMode="tel" autoComplete="tel" maxLength={11} placeholder="请输入手机号" value={phone} onChange={(event) => setPhone(event.target.value.replace(/\D/g, ""))} /></div></label>
          : <label className="form-field"><span>验证码</span><div><input autoFocus className="otp-input" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="6 位验证码" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} /></div></label>}

        {hint && step === "code" && <div className="dev-hint"><Check size={15} />{hint}</div>}
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="login-submit" disabled={busy} type="submit">{busy ? "请稍候…" : step === "phone" ? "获取验证码" : "登录并继续"}<ArrowRight size={18} /></button>
        {step === "code" && <div className="login-secondary"><button type="button" onClick={() => { setStep("phone"); setCode(""); setError(""); }}>修改手机号</button><button type="button" disabled={countdown > 0 || busy} onClick={sendCode}>{countdown > 0 ? `${countdown}s 后重发` : "重新发送"}</button></div>}
        <small><ShieldCheck size={14} />手机号仅用于登录，服务端只保存不可逆摘要。</small>
      </form>
    </section>
  </main>;
}
