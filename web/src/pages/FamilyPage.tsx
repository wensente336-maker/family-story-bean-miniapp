import { ArrowRight, Check, LogOut, Pencil, Plus, Save, ShieldCheck, Trash2, UserRound, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiClientError } from "../services/apiClient";
import {
  addFamilyMember, createFamily, deleteFamilyMember, renameFamily,
  renameFamilyMember
} from "../services/authApi";

export function FamilyPage() {
  const { session, updateFamily, logout } = useAuth();
  const navigate = useNavigate();
  const family = session?.family ?? null;
  const [name, setName] = useState(family?.name ?? "");
  const [ownerNickname, setOwnerNickname] = useState("");
  const [memberNickname, setMemberNickname] = useState("");
  const [editingMemberId, setEditingMemberId] = useState("");
  const [editingNickname, setEditingNickname] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const saveFamily = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || (!family && !ownerNickname.trim())) {
      setError("请填写家庭名称和你的家庭昵称");
      return;
    }
    setBusy(true); setError("");
    try {
      const saved = family ? await renameFamily(family.id, name.trim()) : await createFamily(name.trim(), ownerNickname.trim());
      updateFamily(saved);
      if (!family) navigate("/", { replace: true });
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "保存失败，请重试");
    } finally { setBusy(false); }
  };

  const addMember = async () => {
    if (!family || !memberNickname.trim()) return;
    setBusy(true); setError("");
    try {
      const member = await addFamilyMember(family.id, memberNickname.trim());
      updateFamily({ ...family, members: [...family.members, member] });
      setMemberNickname("");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "添加成员失败");
    } finally { setBusy(false); }
  };

  const beginMemberEdit = (memberId: string, nickname: string) => {
    setEditingMemberId(memberId); setEditingNickname(nickname); setError("");
  };

  const saveMember = async () => {
    if (!family || !editingMemberId || !editingNickname.trim()) return;
    setBusy(true); setError("");
    try {
      const member = await renameFamilyMember(family.id, editingMemberId, editingNickname.trim());
      updateFamily({ ...family, members: family.members.map((item) => item.id === member.id ? member : item) });
      setEditingMemberId(""); setEditingNickname("");
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "修改成员失败");
    } finally { setBusy(false); }
  };

  const removeMember = async (memberId: string, nickname: string) => {
    if (!family || !window.confirm(`确定删除家庭成员“${nickname}”吗？已有转写中的人物关联会被解除。`)) return;
    setBusy(true); setError("");
    try {
      updateFamily(await deleteFamilyMember(family.id, memberId));
      if (editingMemberId === memberId) { setEditingMemberId(""); setEditingNickname(""); }
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : "删除成员失败");
    } finally { setBusy(false); }
  };

  const signOut = () => { logout(); navigate("/login", { replace: true }); };

  return <div className="family-page">
    <header><span className="section-kicker">FAMILY SPACE</span><h1>{family ? "管理家庭空间" : "先创建你们的家庭"}</h1><p>录音、高光、漫画和播客都会归属于这个家庭。</p></header>
    <div className="family-layout">
      <form className="family-form-card" onSubmit={saveFamily}>
        <h2>{family ? "家庭资料" : "创建家庭"}</h2>
        <label className="form-field"><span>家庭名称</span><div><input maxLength={40} placeholder="例如：小满一家" value={name} onChange={(event) => setName(event.target.value)} /></div></label>
        {!family && <label className="form-field"><span>你在家里的昵称</span><div><input maxLength={24} placeholder="例如：妈妈" value={ownerNickname} onChange={(event) => setOwnerNickname(event.target.value)} /></div></label>}
        {error && <div className="form-error" role="alert">{error}</div>}
        <button className="login-submit" disabled={busy} type="submit">{family ? <Save size={18} /> : null}{busy ? "正在保存…" : family ? "保存家庭名称" : "创建并进入家庭"}{!family && <ArrowRight size={18} />}</button>
      </form>

      {family && <section className="family-members-card">
        <div className="family-card-heading"><div><span className="section-kicker">成员</span><h2>{family.members.length} 位家人</h2></div><ShieldCheck size={23} /></div>
        <div className="member-list">{family.members.map((member, index) => <div className={`member-row ${editingMemberId === member.id ? "editing" : ""}`} key={member.id}>
          <span className={`avatar avatar-${index % 3 + 1}`}>{member.nickname.slice(0, 1)}</span>
          {editingMemberId === member.id ? <div className="member-inline-edit"><input autoFocus maxLength={24} value={editingNickname} onChange={(event) => setEditingNickname(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void saveMember(); if (event.key === "Escape") setEditingMemberId(""); }} /><small>最多 24 个字符</small></div> : <div className="member-copy"><strong>{member.nickname}</strong><small>{index === 0 ? "家庭创建者" : "家庭成员"}</small></div>}
          <div className="member-actions">{editingMemberId === member.id ? <><button type="button" aria-label={`保存${member.nickname}`} disabled={busy || !editingNickname.trim()} onClick={() => void saveMember()}><Check size={16} /></button><button type="button" aria-label="取消编辑" disabled={busy} onClick={() => setEditingMemberId("")}><X size={16} /></button></> : <><button type="button" aria-label={`修改${member.nickname}`} disabled={busy} onClick={() => beginMemberEdit(member.id, member.nickname)}><Pencil size={15} /></button>{index > 0 && <button type="button" className="member-delete" aria-label={`删除${member.nickname}`} disabled={busy} onClick={() => void removeMember(member.id, member.nickname)}><Trash2 size={15} /></button>}</>}</div>
        </div>)}</div>
        <div className="member-add"><input maxLength={24} placeholder="输入家庭昵称" value={memberNickname} onChange={(event) => setMemberNickname(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void addMember(); }} /><button type="button" disabled={busy || !memberNickname.trim()} onClick={addMember}><Plus size={18} />添加</button></div>
      </section>}
    </div>
    {family && <button className="logout-button" onClick={signOut}><LogOut size={17} />退出当前账号</button>}
    {!family && <div className="family-privacy"><UserRound size={18} /><span>创建后可以继续添加孩子、伴侣和长辈的家庭昵称。</span></div>}
  </div>;
}
