import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {vi,afterEach,it,expect} from 'vitest';
import {App,Fields} from './main';
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('edits a structured approval field',()=>{
  const change=vi.fn();render(<Fields value={{headline:'Hello'}} onChange={change}/>);
  fireEvent.change(screen.getByLabelText('headline'),{target:{value:'New headline'}});
  expect(change).toHaveBeenCalledWith({headline:'New headline'});
});
it('creates a project and exposes the director checkpoint',async()=>{
  const p={id:'1',name:'After Hours',state:'collecting',version:0,messages:[],logs:[],provider:'mock'};
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>({ok:true,json:async()=>options?.method==='POST'?p:[]})));
  render(<App/>);
  fireEvent.click(screen.getByText('New poster +'));
  await waitFor(()=>expect(screen.getByLabelText('Message to Creative Director')).toBeTruthy());
  expect(screen.queryByText('Generate poster ✳')).toBeNull();
});
it('runs an isolated playground agent',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>({ok:true,json:async()=>options?.method==='POST'?{agent:'director',output:{message:'Try this'}}:[]})));
  render(<App/>);fireEvent.click(screen.getByText(/Agent playground/));
  fireEvent.click(screen.getByText('Run Creative Director ↗'));
  await waitFor(()=>expect(screen.getByText(/Try this/)).toBeTruthy());
});
