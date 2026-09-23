let family = {
  id: "11111111-1111-4111-8111-111111111111",
  owner_user_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "小满一家",
  members: [{
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    nickname: "妈妈",
    character_profile: {},
    voice_consent: false,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z"
  }],
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z"
};

const HOME_FIXTURE = {
  family: {
    id: "11111111-1111-4111-8111-111111111111",
    name: "小满一家",
    memberLabels: ["爸", "妈", "满"]
  },
  processing: {
    recordingId: "22222222-2222-4222-8222-222222222222",
    jobId: "33333333-3333-4333-8333-333333333333",
    title: "周日晚餐",
    detail: "正在发现值得留下的时刻",
    stage: "ANALYZING",
    progress: 68
  },
  moments: [
    {
      id: "44444444-4444-4444-8444-444444444441",
      recordingId: "22222222-2222-4222-8222-222222222222",
      theme: "童言童语",
      durationMs: 48000,
      duration: "00:48",
      title: "月亮是天空的夜灯",
      quote: "那星星就是忘记关掉的小灯吗？",
      color: "sun"
    },
    {
      id: "44444444-4444-4444-8444-444444444442",
      recordingId: "22222222-2222-4222-8222-222222222222",
      theme: "家庭趣事",
      durationMs: 72000,
      duration: "01:12",
      title: "爸爸的海水蛋糕",
      quote: "爸爸，你是不是把盐当成糖啦？",
      color: "coral"
    }
  ]
};

function getHomeData() {
  return Promise.resolve(JSON.parse(JSON.stringify({
    ...HOME_FIXTURE,
    family: { ...HOME_FIXTURE.family, id: family.id, name: family.name }
  })));
}

function wechatLogin() {
  return Promise.resolve({
    access_token: "mock-access-token",
    token_type: "Bearer",
    expires_at: Math.floor(Date.now() / 1000) + 7200,
    user_id: family.owner_user_id,
    family: JSON.parse(JSON.stringify(family))
  });
}

function getSession() {
  return Promise.resolve({ user_id: family.owner_user_id, family: JSON.parse(JSON.stringify(family)) });
}

function createFamily(input) {
  family = { ...family, name: input.name, members: [{ ...family.members[0], nickname: input.owner_nickname }] };
  return Promise.resolve(JSON.parse(JSON.stringify(family)));
}

function renameFamily(_familyId, name) {
  family = { ...family, name };
  return Promise.resolve(JSON.parse(JSON.stringify(family)));
}

function addFamilyMember(_familyId, nickname) {
  const member = {
    id: `mock-member-${family.members.length + 1}`,
    nickname,
    character_profile: {},
    voice_consent: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };
  family.members.push(member);
  return Promise.resolve(JSON.parse(JSON.stringify(member)));
}

module.exports = { getHomeData, wechatLogin, getSession, createFamily, renameFamily, addFamilyMember };
