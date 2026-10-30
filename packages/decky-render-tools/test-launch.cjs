// SPDX-License-Identifier: BSD-3-Clause
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync(process.argv[2] || require('path').join(__dirname,'launch.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const context={exports:{}};vm.runInNewContext(code,context);const edit=context.exports.framegenOptions;
const examples=['','-dx12','/usr/libexec/armada/armada-game-launch ~/.lsfg %command%', 'env VAR="two  spaces" "/a path/wrapper" %command% --argument="x y"'];
for(const input of examples){const on=edit(input,true);assert.equal(edit(on,true),on);assert.equal((on.match(/\/usr\/bin\/kettle-fg/g)||[]).length,1);assert.equal(edit(input,false),input);const off=edit(on,false);assert(!off.includes('/usr/bin/kettle-fg'));assert(on.indexOf('/usr/bin/kettle-fg')<on.indexOf('%command%'));if(input.includes('%command%'))assert.equal(off,input);}
assert.equal(edit('/bin/another-kettle-fg %command%',false),'/bin/another-kettle-fg %command%');
console.log('Launch-option tests: quoted paths, existing wrappers, arguments, repeat enable and own-wrapper removal passed.');
